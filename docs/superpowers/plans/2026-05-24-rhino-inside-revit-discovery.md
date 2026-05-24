# Rhino.Inside Revit Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Rhino.Inside Revit publish authoritative RookNative discovery metadata that MCP can discover and target without an explicit-port bypass.

**Architecture:** Native and MCP resolve the same deterministic per-user discovery root for new RookNative records, while MCP also enumerates legacy `%TEMP%\rook` as a compatibility read path for producers that are not updated in this plan. RookNative writes `instance-<host-process-pid>-native.json` after the native HTTP bridge starts, logs durable best-effort publication diagnostics, and both native startup cleanup and MCP stale cleanup preserve live Revit-hosted records. MCP routing continues to trust discovery only; explicit `port` selects a discovered target or returns `requested_port_not_discovered` without probing HTTP.

**Tech Stack:** Rhino 8 C++ SDK, Visual Studio 2022 v143/MFC, C++17 `std::filesystem`, nlohmann/json, Python 3 MCP server, pytest, PowerShell source guards.

---

## File Structure

- Modify `src/RookNative/RookServer.cpp`: resolve the shared discovery root, write native discovery diagnostics, verify post-rename file visibility, and log cleanup/removal decisions.
- Modify `src/RookNative/RookServer.h`: update discovery comments and keep private helper signatures aligned with `RookServer.cpp`.
- Modify `mcp_server/src/rook/bridge.py`: add shared discovery-root resolution and diagnostics, enumerate both primary and legacy discovery folders for compatibility, keep `DISCOVERY_FOLDER` monkeypatchable for tests, and preserve Rhino.Inside discovery records during stale cleanup.
- Modify `mcp_server/src/rook/targeting.py`: return `requested_port_not_discovered` for explicit-port misses and include discovery diagnostics in the error payload.
- Modify `mcp_server/tests/test_bridge.py`: cover shared root resolution, diagnostics, Rhino.Inside record parsing, and stale cleanup for live/dead Revit-hosted records.
- Modify `mcp_server/tests/test_multi_instance_targeting.py`: cover explicit-port selection and strict explicit-port miss diagnostics.
- Create `scripts/tests/rhino-inside-discovery-guards.tests.ps1`: static/source guards for native discovery fields, diagnostics, post-rename verification, and cleanup logging.
- Modify `docs/superpowers/specs/2026-05-24-rhino-inside-revit-discovery-design.md`: already done; no implementation task should edit the spec unless code reality forces a design change.

---

### Task 1: MCP Shared Discovery Root

**Files:**
- Modify: `mcp_server/src/rook/bridge.py`
- Modify: `mcp_server/tests/test_bridge.py`

- [ ] **Step 1: Write failing root-resolution and compatibility-read tests**

First update the existing `discovery_dir` fixture in `mcp_server/tests/test_bridge.py` so tests remain isolated after MCP supports multiple discovery folders:

```python
@pytest.fixture
def discovery_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [tmp_path])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    return tmp_path
```

Then append these tests near that fixture:

```python
def test_resolve_discovery_folder_prefers_localappdata(tmp_path: Path) -> None:
    env = {"LOCALAPPDATA": str(tmp_path / "LocalAppData")}

    folder, folders, diagnostics = bridge.resolve_discovery_folder(env=env, temp_root=tmp_path / "Temp")

    assert folder == tmp_path / "LocalAppData" / "Rook" / "discovery"
    assert folders == [folder, tmp_path / "Temp" / "rook"]
    assert diagnostics["selection"] == "localappdata"
    assert diagnostics["localAppData"] == str(tmp_path / "LocalAppData")
    assert diagnostics["tempRoot"] == str(tmp_path / "Temp")
    assert diagnostics["legacyTempDiscoveryFolder"] == str(tmp_path / "Temp" / "rook")
    assert diagnostics["discoveryFolders"] == [str(folder), str(tmp_path / "Temp" / "rook")]


def test_resolve_discovery_folder_falls_back_to_temp(tmp_path: Path) -> None:
    folder, folders, diagnostics = bridge.resolve_discovery_folder(env={}, temp_root=tmp_path / "Temp")

    assert folder == tmp_path / "Temp" / "rook"
    assert folders == [folder]
    assert diagnostics["selection"] == "temp"
    assert diagnostics["localAppData"] is None
    assert diagnostics["tempRoot"] == str(tmp_path / "Temp")
    assert diagnostics["discoveryFolders"] == [str(folder)]


def test_discovery_diagnostics_reports_current_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path / "selected")
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [tmp_path / "selected", tmp_path / "legacy"])
    monkeypatch.setattr(
        bridge,
        "_DISCOVERY_FOLDER_DIAGNOSTICS",
        {
            "selection": "localappdata",
            "localAppData": str(tmp_path / "LocalAppData"),
            "tempRoot": str(tmp_path / "Temp"),
            "legacyTempDiscoveryFolder": str(tmp_path / "Temp" / "rook"),
            "discoveryFolders": [str(tmp_path / "selected"), str(tmp_path / "legacy")],
        },
    )

    diagnostics = bridge.discovery_diagnostics()

    assert diagnostics["discoveryFolder"] == str(tmp_path / "selected")
    assert diagnostics["discoveryFolders"] == [str(tmp_path / "selected"), str(tmp_path / "legacy")]
    assert diagnostics["selection"] == "localappdata"
    assert diagnostics["tempRoot"] == str(tmp_path / "Temp")


def test_discover_instances_reads_legacy_folder_when_primary_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = tmp_path / "primary"
    legacy = tmp_path / "legacy"
    primary.mkdir()
    legacy.mkdir()
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", primary)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [primary, legacy])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    _write_instance(
        legacy / "instance-rc-7101.json",
        {
            "host": "127.0.0.1",
            "port": 9960,
            "processId": 7101,
            "pluginType": "roadcreator",
        },
    )

    instances = bridge.discover_instances()

    assert len(instances) == 1
    assert instances[0]["pluginType"] == "roadcreator"
    assert instances[0]["port"] == 9960
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest mcp_server\tests\test_bridge.py -k "resolve_discovery_folder or discovery_diagnostics or legacy_folder" -q
```

Expected: FAIL because `bridge.resolve_discovery_folder`, `bridge.DISCOVERY_FOLDERS`, and `bridge.discovery_diagnostics` do not exist.

- [ ] **Step 3: Implement shared root resolution in MCP**

In `mcp_server/src/rook/bridge.py`, change the imports and discovery constant block to:

```python
import ctypes
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator, Mapping
```

Replace:

```python
# Discovery folder (matches C# side)
DISCOVERY_FOLDER = Path(tempfile.gettempdir()) / "rook"
```

with:

```python
def resolve_discovery_folder(
    *,
    env: Mapping[str, str] | None = None,
    temp_root: str | Path | None = None,
) -> tuple[Path, list[Path], dict[str, Any]]:
    """Resolve primary and compatibility discovery roots used by MCP."""
    source_env = os.environ if env is None else env
    resolved_temp_root = Path(temp_root) if temp_root is not None else Path(tempfile.gettempdir())
    local_app_data = source_env.get("LOCALAPPDATA")
    legacy_temp_discovery = resolved_temp_root / "rook"

    if local_app_data:
        selected = Path(local_app_data) / "Rook" / "discovery"
        selection = "localappdata"
    else:
        selected = legacy_temp_discovery
        selection = "temp"

    folders = [selected]
    if legacy_temp_discovery != selected:
        folders.append(legacy_temp_discovery)

    diagnostics = {
        "selection": selection,
        "localAppData": local_app_data,
        "tempRoot": str(resolved_temp_root),
        "legacyTempDiscoveryFolder": str(legacy_temp_discovery),
        "discoveryFolders": [str(folder) for folder in folders],
    }

    return selected, folders, diagnostics


DISCOVERY_FOLDER, DISCOVERY_FOLDERS, _DISCOVERY_FOLDER_DIAGNOSTICS = resolve_discovery_folder()


def discovery_diagnostics() -> dict[str, Any]:
    diagnostics = dict(_DISCOVERY_FOLDER_DIAGNOSTICS)
    diagnostics["discoveryFolder"] = str(DISCOVERY_FOLDER)
    diagnostics["discoveryFolders"] = [str(folder) for folder in DISCOVERY_FOLDERS]
    return diagnostics
```

Then update the loop in `_cleanup_stale_discovery_files()` so it enumerates every folder in `DISCOVERY_FOLDERS` while keeping the existing per-file cleanup body:

```python
    patterns = [
        "instance-*.json",
        "native-*.json",
        "chat-service-*.json",
        "companion-*.json",
        "chirp-service-*.json",
    ]
    seen: set[Path] = set()
    for discovery_folder in DISCOVERY_FOLDERS:
        if not discovery_folder.exists():
            continue
        for pattern in patterns:
            for file in discovery_folder.glob(pattern):
                if file in seen:
                    continue
                seen.add(file)
                try:
                    data = json.loads(file.read_text(encoding="utf-8"))
                    pid = data.get("processId") or data.get("pid")
                    if pid and not _is_pid_alive(int(pid)):
                        logger.debug(f"Removing stale discovery file {file.name} (PID {pid} dead)")
                        file.unlink(missing_ok=True)
                        continue

                    if file.name.startswith("instance-"):
                        surviving_instances.append(data)
                except Exception:
                    try:
                        file.unlink(missing_ok=True)
                    except Exception:
                        pass
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
python -m pytest mcp_server\tests\test_bridge.py -k "resolve_discovery_folder or discovery_diagnostics or legacy_folder" -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server\src\rook\bridge.py mcp_server\tests\test_bridge.py
git commit -m "test: cover mcp discovery root resolution"
```

---

### Task 2: MCP Rhino.Inside Discovery And Cleanup Contract

**Files:**
- Modify: `mcp_server/tests/test_bridge.py`
- Modify: `mcp_server/src/rook/bridge.py`

- [ ] **Step 1: Write Rhino.Inside discovery and cleanup tests**

Append these tests near the existing discovery cleanup tests in `mcp_server/tests/test_bridge.py`:

```python
def test_discover_instances_accepts_rhino_inside_native_record(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-528-native.json",
        {
            "host": "127.0.0.1",
            "port": 57011,
            "processId": 528,
            "pluginType": "native",
            "pluginVersion": "1.5.8",
            "rhinoInside": True,
            "capabilities": {"ghProvider": "callback", "ghRoutes": []},
        },
    )

    instances = bridge.discover_instances()

    assert len(instances) == 1
    assert instances[0]["port"] == 57011
    assert instances[0]["processId"] == 528
    assert instances[0]["pluginType"] == "native"
    assert instances[0]["rhinoInside"] is True
    assert instances[0]["capabilities"]["ghProvider"] == "callback"


def test_cleanup_keeps_live_rhino_inside_native_record(discovery_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = discovery_dir / "instance-528-native.json"
    _write_instance(
        path,
        {
            "host": "127.0.0.1",
            "port": 57011,
            "processId": 528,
            "pluginType": "native",
            "rhinoInside": True,
        },
    )
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: pid == 528)

    survivors = bridge._cleanup_stale_discovery_files()

    assert path.exists()
    assert len(survivors) == 1
    assert survivors[0]["processId"] == 528


def test_cleanup_removes_dead_rhino_inside_native_record(discovery_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = discovery_dir / "instance-528-native.json"
    _write_instance(
        path,
        {
            "host": "127.0.0.1",
            "port": 57011,
            "processId": 528,
            "pluginType": "native",
            "rhinoInside": True,
        },
    )
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: False)

    survivors = bridge._cleanup_stale_discovery_files()

    assert not path.exists()
    assert survivors == []
```

- [ ] **Step 2: Run tests and inspect result**

Run:

```powershell
python -m pytest mcp_server\tests\test_bridge.py -k "rhino_inside_native_record" -q
```

Expected: these may already PASS because current cleanup uses `processId`; if they pass, they lock the contract before native changes.

- [ ] **Step 3: Make minimal MCP cleanup change only if a test fails**

If cleanup tests unexpectedly read from real user discovery folders, update the `discovery_dir` fixture exactly as specified in Task 1 so it monkeypatches both `bridge.DISCOVERY_FOLDER` and `bridge.DISCOVERY_FOLDERS` to the temporary test path.

If normalization drops `rhinoInside`, keep it by ensuring `_normalize_instance()` copies the input before assigning defaults:

```python
    data = dict(data)
    data["pluginType"] = plugin_type
    data["capabilities"] = capabilities
```

This block already exists on current `main`; do not duplicate it.

- [ ] **Step 4: Run the full bridge test file**

Run:

```powershell
python -m pytest mcp_server\tests\test_bridge.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server\src\rook\bridge.py mcp_server\tests\test_bridge.py
git commit -m "test: cover rhino inside discovery cleanup"
```

---

### Task 3: Strict Explicit-Port MCP Diagnostics

**Files:**
- Modify: `mcp_server/src/rook/targeting.py`
- Modify: `mcp_server/tests/test_multi_instance_targeting.py`

- [ ] **Step 1: Write failing explicit-port diagnostic tests**

Replace `test_explicit_missing_port_returns_target_error` in `mcp_server/tests/test_multi_instance_targeting.py` with:

```python
def test_explicit_missing_port_returns_requested_port_not_discovered(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    monkeypatch.setattr(
        targeting,
        "discovery_diagnostics",
        lambda: {
            "discoveryFolder": r"C:\Users\bring\AppData\Local\Rook\discovery",
            "discoveryFolders": [
                r"C:\Users\bring\AppData\Local\Rook\discovery",
                r"C:\Users\bring\AppData\Local\Temp\rook",
            ],
            "selection": "localappdata",
            "tempRoot": r"C:\Users\bring\AppData\Local\Temp",
            "legacyTempDiscoveryFolder": r"C:\Users\bring\AppData\Local\Temp\rook",
        },
    )
    targeting.clear_active_target()

    route = targeting.resolve_tool_route("rhino_document", explicit_port=9999)
    result = targeting.route_error_result(route)

    assert route.success is False
    assert route.error == "requested_port_not_discovered"
    assert route.target is None
    assert result["success"] is False
    assert result["data"]["error"] == "requested_port_not_discovered"
    assert result["data"]["requestedPort"] == 9999
    assert result["data"]["discoveryFolder"] == r"C:\Users\bring\AppData\Local\Rook\discovery"
    assert result["data"]["discoveryFolders"][1] == r"C:\Users\bring\AppData\Local\Temp\rook"
    assert result["data"]["selection"] == "localappdata"
    assert result["data"]["instances"][0]["port"] == 9950
```

Add this test next to `test_explicit_port_wins_over_active_binding`:

```python
def test_explicit_port_still_selects_discovered_target(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_document", explicit_port=9951)

    assert route.success is True
    assert route.target == targeting.InstanceRef(9951, 7102)
    assert route.selection == "explicit"
```

Add this test to keep malformed MCP arguments from producing misleading requested-port diagnostics:

```python
@pytest.mark.parametrize("raw_port", ["9951", 0, -1])
def test_invalid_explicit_port_returns_invalid_requested_port(monkeypatch, raw_port):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "B.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_document", explicit_port=raw_port)
    result = targeting.route_error_result(route)

    assert route.success is False
    assert route.error == "invalid_requested_port"
    assert result["success"] is False
    assert result["data"]["error"] == "invalid_requested_port"
    assert "requestedPort" not in result["data"]
    assert result["data"]["invalidPort"] == repr(raw_port)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest mcp_server\tests\test_multi_instance_targeting.py -k "explicit" -q
```

Expected: FAIL because explicit-port misses still return `rhino_target_unavailable`, invalid raw ports are not handled explicitly, and `targeting.discovery_diagnostics` is not imported.

- [ ] **Step 3: Add route fields and diagnostics import**

In `mcp_server/src/rook/targeting.py`, change:

```python
from .bridge import call_rhino, discover_instances
```

to:

```python
from .bridge import call_rhino, discover_instances, discovery_diagnostics
```

Add a field to `ToolRoute`:

```python
    requested_port: int | None = None
    invalid_port: object | None = None
```

Also relax the runtime-facing `resolve_tool_route()` annotation because MCP arguments can arrive before schema coercion:

```python
def resolve_tool_route(name: str, *, explicit_port: object | None = None) -> ToolRoute:
```

- [ ] **Step 4: Return strict explicit-port errors**

Add this helper near `instance_ref_from_instance()`:

```python
def _valid_explicit_port(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None
```

In `resolve_tool_route()`, normalize raw MCP input immediately after `_PANEL_TARGET_CONFIG_ERROR` handling and before the panel-lock branch, so every later explicit-port comparison receives either a positive integer or `None`:

```python
    if explicit_port is not None:
        normalized_port = _valid_explicit_port(explicit_port)
        if normalized_port is None:
            return ToolRoute(
                success=False,
                error="invalid_requested_port",
                invalid_port=explicit_port,
                instances=instances,
            )
        explicit_port = normalized_port
```

In `resolve_tool_route()`, replace the explicit-port miss block:

```python
        return ToolRoute(
            success=False,
            error="rhino_target_unavailable",
            instances=instances,
        )
```

with:

```python
        return ToolRoute(
            success=False,
            error="requested_port_not_discovered",
            requested_port=explicit_port,
            instances=instances,
        )
```

- [ ] **Step 5: Add the user-facing error payload**

In `route_error_result()`, add this branch before the existing `rhino_target_unavailable` branch:

```python
    if route.error == "requested_port_not_discovered":
        diagnostics = discovery_diagnostics()
        return _error_result(
            "requested_port_not_discovered",
            message=(
                "No discovered RookNative instance owns the requested port. "
                "Native discovery publication may have failed or MCP may be looking in a different discovery folder."
            ),
            requestedPort=route.requested_port,
            discoveryFolder=diagnostics.get("discoveryFolder"),
            discoveryFolders=diagnostics.get("discoveryFolders"),
            selection=diagnostics.get("selection"),
            tempRoot=diagnostics.get("tempRoot"),
            legacyTempDiscoveryFolder=diagnostics.get("legacyTempDiscoveryFolder"),
            instances=route.instances or [],
        )
    if route.error == "invalid_requested_port":
        return _error_result(
            "invalid_requested_port",
            message="Explicit Rhino port must be a positive integer discovered in Rook metadata.",
            invalidPort=repr(route.invalid_port),
            instances=route.instances or [],
        )
```

- [ ] **Step 6: Run targeting tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_multi_instance_targeting.py -k "explicit" -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add mcp_server\src\rook\targeting.py mcp_server\tests\test_multi_instance_targeting.py
git commit -m "fix: report undiscovered explicit rhino ports"
```

---

### Task 4: Native Discovery Static Guards

**Files:**
- Create: `scripts/tests/rhino-inside-discovery-guards.tests.ps1`

- [ ] **Step 1: Add native source guard script**

Create `scripts/tests/rhino-inside-discovery-guards.tests.ps1` with:

```powershell
$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$RookServerCpp = Join-Path $RepoRoot 'src\RookNative\RookServer.cpp'
$RookServerHeader = Join-Path $RepoRoot 'src\RookNative\RookServer.h'

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Expected,
        [string]$Message
    )

    if (-not $Text.Contains($Expected)) {
        throw $Message
    }
}

function Assert-Matches {
    param(
        [string]$Text,
        [string]$Pattern,
        [string]$Message
    )

    if ($Text -notmatch $Pattern) {
        throw $Message
    }
}

function Test-NativeDiscoveryUsesSharedRoot {
    $content = Get-Content -Path $RookServerCpp -Raw

    Assert-Contains -Text $content -Expected 'ResolveDiscoveryRootInfo' -Message 'RookServer.cpp must resolve discovery root details in one helper.'
    Assert-Contains -Text $content -Expected 'nativeTempRoot' -Message 'RookServer.cpp must log the native temp root separately.'
    Assert-Contains -Text $content -Expected 'sharedDiscoveryFolder' -Message 'RookServer.cpp must resolve a shared discovery folder.'
    Assert-Contains -Text $content -Expected 'LOCALAPPDATA' -Message 'Native discovery must prefer the deterministic per-user LOCALAPPDATA root.'
    Assert-Matches -Text $content -Pattern '"Rook"\s*/\s*"discovery"' -Message 'Native discovery must construct the shared per-user Rook discovery child.'
    Assert-Contains -Text $content -Expected 'selectionBranch' -Message 'Native diagnostics must report the root selection branch.'
}

function Test-NativeDiscoveryPublishesRhinoInsideMetadata {
    $content = Get-Content -Path $RookServerCpp -Raw

    Assert-Contains -Text $content -Expected 'info["processId"] = ::GetCurrentProcessId();' -Message 'Discovery JSON must publish host process ID.'
    Assert-Contains -Text $content -Expected 'info["rhinoInside"] = CRookNativePlugin::IsRhinoInside();' -Message 'Discovery JSON must publish rhinoInside.'
    Assert-Contains -Text $content -Expected 'info["pluginType"] = "native";' -Message 'Discovery JSON must publish native plugin type.'
    Assert-Contains -Text $content -Expected 'info["capabilities"]' -Message 'Discovery JSON must publish capabilities.'
}

function Test-NativeDiscoveryDiagnosticsAreDurable {
    $content = Get-Content -Path $RookServerCpp -Raw

    Assert-Contains -Text $content -Expected 'native-discovery-' -Message 'Native diagnostics must write a durable per-process diagnostic log.'
    Assert-Contains -Text $content -Expected 'WriteDiscoveryDiagnostic' -Message 'Native diagnostics must have a centralized best-effort writer.'
    Assert-Contains -Text $content -Expected 'post-rename verification' -Message 'Native diagnostics must record post-rename verification.'
    Assert-Contains -Text $content -Expected 'fs::file_size' -Message 'Post-rename verification must check final file size.'
    Assert-Matches -Text $content -Pattern 'nlohmann::json::parse\(' -Message 'Post-rename verification must read back or parse the final file.'
    Assert-Contains -Text $content -Expected 'MoveFileExW' -Message 'Atomic rename must remain explicit.'
    Assert-Contains -Text $content -Expected 'GetLastError' -Message 'Rename diagnostics must include Windows error code.'
}

function Test-NativeCleanupDiagnostics {
    $content = Get-Content -Path $RookServerCpp -Raw

    Assert-Contains -Text $content -Expected 'cleanup scan' -Message 'Startup cleanup must log scan decisions.'
    Assert-Contains -Text $content -Expected 'jsonPid=' -Message 'Startup cleanup must log JSON PID decisions for non-filename discovery records.'
    Assert-Contains -Text $content -Expected 'remove-on-unload' -Message 'Unload cleanup must log remove-on-unload decisions.'
    Assert-Contains -Text $content -Expected 'IsPidAlive' -Message 'Cleanup must keep using PID liveness.'
}

function Test-HeaderDocumentsSharedDiscoveryRoot {
    $content = Get-Content -Path $RookServerHeader -Raw

    Assert-Contains -Text $content -Expected 'shared discovery root' -Message 'RookServer.h must document shared discovery root instead of only %TEMP%/rook.'
}

Test-NativeDiscoveryUsesSharedRoot
Test-NativeDiscoveryPublishesRhinoInsideMetadata
Test-NativeDiscoveryDiagnosticsAreDurable
Test-NativeCleanupDiagnostics
Test-HeaderDocumentsSharedDiscoveryRoot

Write-Host 'rhino-inside-discovery-guards.tests.ps1 passed'
```

- [ ] **Step 2: Run guard and verify failure**

Run:

```powershell
scripts\tests\rhino-inside-discovery-guards.tests.ps1
```

Expected: FAIL before native implementation because `ResolveDiscoveryRootInfo`, durable diagnostic strings, JSON PID cleanup diagnostics, and post-rename verification are absent.

- [ ] **Step 3: Commit after Task 5 passes**

Do not commit a failing guard by itself. Commit this new file together with the native implementation in Task 5.

---

### Task 5: Native Shared Root, Diagnostics, And Post-Rename Verification

**Files:**
- Modify: `src/RookNative/RookServer.cpp`
- Modify: `src/RookNative/RookServer.h`
- Create: `scripts/tests/rhino-inside-discovery-guards.tests.ps1`

- [ ] **Step 1: Update header comments**

In `src/RookNative/RookServer.h`, replace:

```cpp
// discovery file in %TEMP%/rook/.
```

with:

```cpp
// discovery file under the shared discovery root resolved by native and MCP.
// The default shared root is %LOCALAPPDATA%/Rook/discovery, with %TEMP%/rook
// retained only as the no-LOCALAPPDATA fallback.
```

- [ ] **Step 2: Add native discovery helper types**

In `src/RookNative/RookServer.cpp`, add after `constexpr const char* kNativeBindHost = "127.0.0.1";`:

```cpp
    struct DiscoveryRootInfo
    {
        fs::path nativeTempRoot;
        fs::path legacyTempDiscoveryFolder;
        fs::path sharedDiscoveryFolder;
        std::string selectionBranch;
        std::string localAppData;
        std::string tempEnv;
        std::string tmpEnv;
    };
```

Add these helper functions in the anonymous namespace:

```cpp
    std::wstring GetEnvironmentVariableWide(const wchar_t* name)
    {
        DWORD required = ::GetEnvironmentVariableW(name, nullptr, 0);
        if (required == 0)
            return L"";

        std::wstring value(required, L'\0');
        DWORD written = ::GetEnvironmentVariableW(name, value.data(), required);
        if (written == 0 || written >= required)
            return L"";

        value.resize(written);
        return value;
    }

    std::string WideToUtf8String(const std::wstring& input)
    {
        if (input.empty())
            return "";

        const int size = ::WideCharToMultiByte(CP_UTF8, 0, input.c_str(), -1, nullptr, 0, nullptr, nullptr);
        if (size <= 1)
            return "";

        std::string result(static_cast<size_t>(size - 1), '\0');
        ::WideCharToMultiByte(CP_UTF8, 0, input.c_str(), -1, result.data(), size, nullptr, nullptr);
        return result;
    }

    std::string PathToUtf8String(const fs::path& path)
    {
        return WideToUtf8String(path.wstring());
    }

    DiscoveryRootInfo ResolveDiscoveryRootInfo()
    {
        DiscoveryRootInfo info;
        info.nativeTempRoot = fs::temp_directory_path();
        info.legacyTempDiscoveryFolder = info.nativeTempRoot / "rook";
        info.localAppData = WideToUtf8String(GetEnvironmentVariableWide(L"LOCALAPPDATA"));
        info.tempEnv = WideToUtf8String(GetEnvironmentVariableWide(L"TEMP"));
        info.tmpEnv = WideToUtf8String(GetEnvironmentVariableWide(L"TMP"));

        if (!info.localAppData.empty())
        {
            info.sharedDiscoveryFolder = fs::path(GetEnvironmentVariableWide(L"LOCALAPPDATA")) / "Rook" / "discovery";
            info.selectionBranch = "localappdata";
        }
        else
        {
            info.sharedDiscoveryFolder = info.legacyTempDiscoveryFolder;
            info.selectionBranch = "temp";
        }

        return info;
    }
```

- [ ] **Step 3: Add best-effort diagnostic writer**

Add this helper after `ResolveDiscoveryRootInfo()`:

```cpp
    void WriteDiscoveryDiagnostic(const DiscoveryRootInfo& rootInfo, DWORD pid, const std::string& message)
    {
        try
        {
            fs::create_directories(rootInfo.sharedDiscoveryFolder);
            const fs::path logPath = rootInfo.sharedDiscoveryFolder / ("native-discovery-" + std::to_string(pid) + ".log");
            std::ofstream log(logPath, std::ios::app);
            if (!log.is_open())
                return;

            const auto now = std::chrono::system_clock::now();
            const auto time = std::chrono::system_clock::to_time_t(now);
            std::tm tm_buf = {};
            if (localtime_s(&tm_buf, &time) == 0)
            {
                log << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%S");
            }
            else
            {
                log << time;
            }

            log
                << " pid=" << pid
                << " selectionBranch=" << rootInfo.selectionBranch
                << " nativeTempRoot=" << PathToUtf8String(rootInfo.nativeTempRoot)
                << " sharedDiscoveryFolder=" << PathToUtf8String(rootInfo.sharedDiscoveryFolder)
                << " legacyTempDiscoveryFolder=" << PathToUtf8String(rootInfo.legacyTempDiscoveryFolder)
                << " TEMP=" << rootInfo.tempEnv
                << " TMP=" << rootInfo.tmpEnv
                << " " << message
                << "\n";
        }
        catch (...)
        {
            RhinoApp().Print(L"RookNative: warning - failed to write discovery diagnostics\n");
        }
    }
```

- [ ] **Step 4: Use shared root in discovery path**

Replace `GetDiscoveryFolder()` with:

```cpp
std::string CRookServer::GetDiscoveryFolder()
{
    return ResolveDiscoveryRootInfo().sharedDiscoveryFolder.string();
}
```

Keep `GetDiscoveryFilePath()` filename semantics unchanged:

```cpp
std::string CRookServer::GetDiscoveryFilePath()
{
    DWORD pid = ::GetCurrentProcessId();
    return GetDiscoveryFolder() + "\\instance-" + std::to_string(pid) + "-native.json";
}
```

- [ ] **Step 5: Add write diagnostics and post-rename verification**

In `WriteDiscoveryFile()`, create `rootInfo` once and use it for folder/path creation:

```cpp
        const DiscoveryRootInfo rootInfo = ResolveDiscoveryRootInfo();
        const DWORD pid = ::GetCurrentProcessId();
        const std::string folder = rootInfo.sharedDiscoveryFolder.string();
        fs::create_directories(folder);
        WriteDiscoveryDiagnostic(rootInfo, pid, "write start rhinoInside=" + std::string(CRookNativePlugin::IsRhinoInside() ? "true" : "false") + " port=" + std::to_string(m_port));
```

After a failed temp file open, add:

```cpp
            WriteDiscoveryDiagnostic(rootInfo, pid, "temp file open failed path=" + tmp_path);
```

After `MoveFileExW` succeeds, add:

```cpp
        bool finalExists = false;
        uintmax_t finalSize = 0;
        bool readBackJson = false;
        try
        {
            finalExists = fs::exists(m_discovery_path);
            if (finalExists)
                finalSize = fs::file_size(m_discovery_path);

            std::ifstream verify(m_discovery_path);
            if (verify.is_open())
            {
                const auto parsed = nlohmann::json::parse(verify, nullptr, false);
                readBackJson = !parsed.is_discarded();
            }
        }
        catch (...)
        {
            readBackJson = false;
        }

        WriteDiscoveryDiagnostic(
            rootInfo,
            pid,
            "post-rename verification path=" + m_discovery_path
                + " exists=" + std::string(finalExists ? "true" : "false")
                + " size=" + std::to_string(finalSize)
                + " json=" + std::string(readBackJson ? "true" : "false"));
```

Inside the `MoveFileExW` failure branch, before throwing, add:

```cpp
            WriteDiscoveryDiagnostic(rootInfo, pid, "MoveFileExW failed error=" + std::to_string(error) + " tmp=" + tmp_path + " final=" + m_discovery_path);
```

Inside the catch block, compute a fresh root info and log the exception:

```cpp
        const DiscoveryRootInfo rootInfo = ResolveDiscoveryRootInfo();
        WriteDiscoveryDiagnostic(rootInfo, ::GetCurrentProcessId(), std::string("write exception message=") + ex.what());
```

- [ ] **Step 6: Add cleanup and unload diagnostics**

In `Start()` cleanup, create root diagnostics before iterating:

```cpp
        const DiscoveryRootInfo rootInfo = ResolveDiscoveryRootInfo();
        const fs::path discoveryFolder = rootInfo.sharedDiscoveryFolder;
        WriteDiscoveryDiagnostic(rootInfo, ::GetCurrentProcessId(), "cleanup scan folder=" + PathToUtf8String(discoveryFolder));
```

When filename PID cleanup keeps or removes a file, log the liveness decision without calling `IsPidAlive(pid)` twice:

```cpp
                    const bool alive = IsPidAlive(pid);
                    WriteDiscoveryDiagnostic(
                        rootInfo,
                        ::GetCurrentProcessId(),
                        "cleanup scan file=" + fileName + " parsedPid=" + std::to_string(pid)
                            + " alive=" + std::string(alive ? "true" : "false"));
                    if (!alive)
                        fs::remove(entry.path());
```

In the JSON PID cleanup branch for `chat-service-*`, `instance-rc-*`, and `companion-*`, log malformed JSON removals, missing PID decisions, and live/dead PID decisions:

```cpp
                    if (data.is_discarded())
                    {
                        WriteDiscoveryDiagnostic(rootInfo, ::GetCurrentProcessId(), "cleanup scan file=" + fileName + " malformedJson=true action=remove");
                        fs::remove(entry.path());
                        continue;
                    }

                    DWORD filePid = 0;
                    if (data.contains("pid") && data["pid"].is_number_integer())
                        filePid = static_cast<DWORD>(data["pid"].get<int>());
                    else if (data.contains("processId") && data["processId"].is_number_integer())
                        filePid = static_cast<DWORD>(data["processId"].get<int>());

                    if (filePid == 0)
                    {
                        WriteDiscoveryDiagnostic(rootInfo, ::GetCurrentProcessId(), "cleanup scan file=" + fileName + " jsonPid=0 action=keep");
                        continue;
                    }

                    const bool alive = IsPidAlive(filePid);
                    WriteDiscoveryDiagnostic(
                        rootInfo,
                        ::GetCurrentProcessId(),
                        "cleanup scan file=" + fileName + " jsonPid=" + std::to_string(filePid)
                            + " alive=" + std::string(alive ? "true" : "false"));
                    if (!alive)
                        fs::remove(entry.path());
```

In `RemoveDiscoveryFile()`, before `fs::remove(m_discovery_path)`, add:

```cpp
            const DiscoveryRootInfo rootInfo = ResolveDiscoveryRootInfo();
            WriteDiscoveryDiagnostic(rootInfo, ::GetCurrentProcessId(), "remove-on-unload path=" + m_discovery_path);
```

- [ ] **Step 7: Run native static guard**

Run:

```powershell
scripts\tests\rhino-inside-discovery-guards.tests.ps1
```

Expected: PASS.

- [ ] **Step 8: Build native plugin if Rhino/MFC toolchain is available**

Run from a normal PowerShell process:

```powershell
cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds. If the machine lacks the Rhino SDK or MSVC 14.44 MFC payload, record the exact failure and do not claim native build verification.

- [ ] **Step 9: Commit**

```powershell
git add src\RookNative\RookServer.cpp src\RookNative\RookServer.h scripts\tests\rhino-inside-discovery-guards.tests.ps1
git commit -m "fix: harden native discovery publication"
```

---

### Task 6: Full Automated Verification

**Files:**
- Read: `mcp_server/tests/test_bridge.py`
- Read: `mcp_server/tests/test_multi_instance_targeting.py`
- Read: `scripts/tests/rhino-inside-discovery-guards.tests.ps1`

- [ ] **Step 1: Run focused MCP tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_bridge.py mcp_server\tests\test_multi_instance_targeting.py -q
```

Expected: PASS.

- [ ] **Step 2: Run native source guard**

Run:

```powershell
scripts\tests\rhino-inside-discovery-guards.tests.ps1
```

Expected: PASS.

- [ ] **Step 3: Run existing release/workflow guard tests touched by this area**

Run:

```powershell
scripts\tests\release-installer-guards.tests.ps1
scripts\tests\deploy-local-testing-guards.tests.ps1
scripts\tests\local-testing-stack-guards.tests.ps1
git diff --check
```

Expected: all PASS.

- [ ] **Step 4: Commit verification-only doc updates if needed**

If verification exposes a necessary command update in a release skill or testing doc, edit that doc and commit it:

```powershell
git add .agents\skills\build-release\SKILL.md .agents\skills\build-release\references\version-locations.md
git commit -m "docs: update discovery release validation"
```

If no doc changed, skip this commit.

---

### Task 7: Live Revit Validation Gate

**Files:**
- Read: `docs/superpowers/specs/2026-05-24-rhino-inside-revit-discovery-design.md`
- Read: `installer/output/Rook-Setup-1.5.8.exe` after the release-candidate installer is built

- [ ] **Step 1: Confirm version/source alignment before live testing**

On the build machine, confirm the installer and native source version match the intended release candidate:

```powershell
(Get-Item .\src\RookNative\x64\Release\RookNative.rhp).VersionInfo.FileVersion
(Get-Item .\installer\output\Rook-Setup-1.5.8.exe).VersionInfo.FileVersion
git rev-parse HEAD
```

Expected: native file version is `1.5.8.0`, installer file version is `1.5.8.0`, and the SHA is the commit intended for the release manifest.

- [ ] **Step 2: Install on the fresh laptop and launch Revit/Rhino.Inside**

Install the release-candidate `Rook-Setup-1.5.8.exe` as the same Windows user who runs Revit. Launch Revit 2024, start Rhino.Inside Revit, and ensure RookNative is loaded in the Revit process.

- [ ] **Step 3: Run non-mutating validation commands on the laptop**

Run in PowerShell on the laptop:

```powershell
$rookRoot = Join-Path $env:LOCALAPPDATA 'Rook\discovery'
$legacyRoot = Join-Path $env:TEMP 'rook'
Write-Host "sharedRoot=$rookRoot"
Write-Host "legacyRoot=$legacyRoot"
Get-ChildItem -Path $rookRoot -Filter 'instance-*-native.json' -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host $_.FullName
    Get-Content $_.FullName -Raw
}
Get-Process Revit -ErrorAction Stop | Select-Object Id, ProcessName, Path
```

Expected: `instance-<RevitPID>-native.json` exists under `$env:LOCALAPPDATA\Rook\discovery`, JSON `processId` equals the Revit PID, `rhinoInside` is `true`, `pluginType` is `native`, and `port` is a valid listening port.

- [ ] **Step 4: Verify bridge and MCP targeting**

Run on the laptop:

```powershell
$json = Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Rook\discovery') -Filter 'instance-*-native.json' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    Get-Content -Raw |
    ConvertFrom-Json
Invoke-WebRequest "http://127.0.0.1:$($json.port)/ping" -UseBasicParsing | Select-Object StatusCode, Content
```

Expected: HTTP status `200` and content contains `{"data":"pong","success":true}`.

From a fresh Codex session on the laptop, call:

```text
mcp__rook__.rhino_ping({})
mcp__rook__.rhino_ping({"port": <json.port>})
```

Expected: both succeed because the port is discovered. A request for a different random port returns `requested_port_not_discovered` and includes the discovery folder plus current instances.

- [ ] **Step 5: Record live validation outcome**

Capture these values for the release manifest or PR comment:

```text
Windows version:
Rhino version:
Revit version:
Rhino.Inside.Revit version:
Rook version:
Git SHA:
Installer SHA256:
Discovery folder:
Discovery file:
Discovery processId:
Revit PID:
Native port:
/ping result:
MCP rhino_ping({}) result:
MCP rhino_ping({"port": nativePort}) result:
Native discovery diagnostic log path:
```

Expected: all fields are populated; failures include the diagnostic log contents.

---

## Final Verification Matrix

- `python -m pytest mcp_server\tests\test_bridge.py mcp_server\tests\test_multi_instance_targeting.py -q`
- `scripts\tests\rhino-inside-discovery-guards.tests.ps1`
- `scripts\tests\release-installer-guards.tests.ps1`
- `scripts\tests\deploy-local-testing-guards.tests.ps1`
- `scripts\tests\local-testing-stack-guards.tests.ps1`
- `git diff --check`
- Native Release build with MSVC `14.44.35207` and Rhino 8 SDK
- Fresh-laptop Revit/Rhino.Inside live validation

## Self-Review

- Spec coverage: shared discovery root is covered in Task 1 and Task 5; legacy compatibility reads are covered in Task 1; no explicit-port bypass and invalid-port handling are covered in Task 3 and Task 7; native diagnostics are covered in Task 4 and Task 5; filename and JSON PID cleanup preservation are covered in Task 2 and Task 5; live Revit validation is covered in Task 7.
- Placeholder scan: this plan contains no unresolved marker text or unspecified implementation steps.
- Type consistency: MCP functions use `Path`, `Mapping[str, str]`, `dict[str, Any]`, and existing `ToolRoute`; native code keeps discovery changes inside `RookServer.cpp` to avoid `.vcxproj` edits.
