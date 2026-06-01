# Rook Ecosystem Phase 1 Capability Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned, evidence-backed runtime capability discovery surface through RookNative without changing route ownership, companion loading, installer layout, or existing availability semantics.

**Architecture:** RookNative remains the only public HTTP/discovery surface and exposes `GET /capabilities` plus additive discovery metadata. Discovery JSON is locator/bootstrap metadata; `GET /capabilities` is the authoritative live runtime capability state. Native state is built from current server/runtime facts, granular bridge callback registration, host state, and the existing companion runtime status file. Managed code only enriches the internal status file with domain evidence; it does not become a public HTTP surface and does not change startup or loading policy.

**Tech Stack:** Rhino 8 C++ SDK, MFC/v143, cpp-httplib, nlohmann/json, C# net48 managed companion, xUnit source/contract tests, Python MCP pytest tests.

---

## Source Documents

- `docs/superpowers/specs/2026-05-31-rook-ecosystem-master-decomposition-design.md`
- `docs/superpowers/specs/2026-05-31-rook-ecosystem-architecture-roadmap.md`
- `docs/CURRENT_ARCHITECTURE.md`
- `src/RookNative/RookServer.cpp`
- `src/RookNative/Handlers/GrasshopperProxyHandler.h`
- `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- `src/Rook/RookPlugin.cs`
- `src/Rook/Startup/CompanionRuntimeStatus.cs`
- `src/Rook/Bim/*`
- `src/RookBim/*`
- `mcp_server/src/rook/bridge.py`

## Phase 1 Boundaries

Phase 1 is descriptive. It reports current behavior and known dependencies; it does not change availability semantics.

Allowed:

- Add `GET /capabilities` to RookNative.
- Add a compact, additive bootstrap capability summary to existing native discovery JSON.
- Keep existing discovery fields `capabilities.ghProvider` and `capabilities.ghRoutes`.
- Split capability state by domain.
- Add granular callback-registration evidence helpers.
- Extend the existing companion runtime status file with internal domain evidence.
- Teach MCP discovery normalization to preserve bootstrap domain data and resolve live domain state from `GET /capabilities`.

Forbidden:

- No route ownership changes.
- No companion loading changes.
- No installer path or registry changes.
- No new public managed HTTP surface.
- No broad "bridge ready" replacement for domain-specific state.
- No Revit API references in `src/Rook`.
- No `.vcxproj` or `.vcxproj.filters` edits in this phase, except for the
  documented native build-system exception below.
- No installer module manifests or full runtime/install correlation.

Documented native build-system exception:

- Phase 1 may add `/bigobj` to the `RookServer.cpp` `ClCompile` item only if
  direct `nlohmann::json` construction for the capability document causes MSVC
  C1128 section-limit failures during the native build.
- This exception exists to preserve the stronger schema implementation:
  `/capabilities` and discovery summaries must be built from structured JSON,
  not hand-built strings or token scraping.
- The exception does not permit new dependencies, route ownership changes,
  companion loading changes, installer path or registry changes, global compiler
  option changes, or `.vcxproj.filters` edits.
- If used, reviewers must confirm the project-file diff is limited to
  `RookServer.cpp` `/bigobj` and that the MSVC 14.44 native build passes.

## Capability Schema V1

The Phase 1 schema is intentionally small but evidence-backed.

Top-level response:

```json
{
  "schemaVersion": 1,
  "generatedUtc": "2026-05-31T12:00:00Z",
  "source": "RookNative",
  "processId": 1234,
  "pluginType": "native",
  "pluginVersion": "1.5.9",
  "rhinoInside": false,
  "domains": []
}
```

Domain record:

```json
{
  "domainId": "bim.rhino_inside_revit",
  "declared": true,
  "installed": "unknown",
  "loaded": false,
  "state": "blocked_by_host",
  "ready": false,
  "reasonCode": "not_rhino_inside",
  "retryable": false,
  "stateSource": "native_host_state",
  "message": "RookBIM is a declared Rook domain, but this Rhino process is not hosted inside Revit.",
  "routes": ["GET /bim/status"],
  "operations": ["status"],
  "diagnostics": ["GET /bim/status"],
  "evidence": [
    {
      "kind": "host",
      "name": "rhinoInside",
      "value": false
    }
  ]
}
```

Required domain IDs for Phase 1:

```text
native.core
native.command_control
gh.bridge
gh.canvas
bim.rhino_inside_revit
chat.ui
vision.media
viewport.capture
block.definition_mutation
mcp.runtime
knowledge.stores
chirp.runtime
licensing.entitlement
```

Allowed `state` values:

```text
ready
degraded
unavailable
not_loaded
loading
blocked_by_host
missing_dependency
failed
unknown
reserved
```

Allowed `installed` values:

```text
present
absent
unknown
reserved
```

## File Structure

- Modify `src/Rook.Tests/Capabilities/CapabilityDiscoverySourceTests.cs`
  - New source/contract tests for domain inventory, schema field names, route registration, and no broad bridge bit.
- Modify `src/RookNative/Handlers/GrasshopperProxyHandler.h`
  - Add granular bridge evidence helper declarations.
- Modify `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
  - Add granular callback registration helpers while preserving `HasGrasshopperBridgeRegistration()` behavior.
- Modify `src/RookNative/RookServer.h`
  - Add `HandleCapabilities`.
- Modify `src/RookNative/RookServer.cpp`
  - Register `GET /capabilities`, add capability document helpers near the existing discovery helpers, and add compact discovery fields.
- Create `src/Rook/Capabilities/CapabilityDomainStatus.cs`
  - Managed internal capability domain record and builder helpers.
- Modify `src/Rook/Startup/CompanionRuntimeStatus.cs`
  - Include managed domain status records in the existing companion status file.
- Modify `src/Rook/RookPlugin.cs`
  - Track panel-registration evidence and pass managed domain status into `CompanionRuntimeStatus`.
- Modify `src/Rook.Tests/Plugin/CompanionRuntimeStatusTests.cs`
  - Assert managed status JSON contains evidence-backed capability domains.
- Create `src/Rook.Tests/Capabilities/ManagedCapabilityDomainStatusTests.cs`
  - Unit tests for managed domain status mapping, including BIM boundary behavior without Revit references.
- Modify `mcp_server/src/rook/bridge.py`
  - Preserve and expose capability domain records during discovery normalization.
- Modify `mcp_server/tests/test_bridge.py`
  - Assert old discovery files still normalize and new domain records are preserved/readable.

## Task 1: Native Source Guards For The Capability Contract

**Files:**

- Create: `src/Rook.Tests/Capabilities/CapabilityDiscoverySourceTests.cs`

- [ ] **Step 1: Add failing source tests for the Phase 1 contract**

Create `src/Rook.Tests/Capabilities/CapabilityDiscoverySourceTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using Xunit;

namespace Rook.Tests.Capabilities
{
    public class CapabilityDiscoverySourceTests
    {
        private static readonly string[] RequiredDomains =
        {
            "native.core",
            "native.command_control",
            "gh.bridge",
            "gh.canvas",
            "bim.rhino_inside_revit",
            "chat.ui",
            "vision.media",
            "viewport.capture",
            "block.definition_mutation",
            "mcp.runtime",
            "knowledge.stores",
            "chirp.runtime",
            "licensing.entitlement",
        };

        [Fact]
        public void RookServer_RegistersPublicCapabilitiesRouteOnNativeServer()
        {
            var header = ReadSourceFile("src", "RookNative", "RookServer.h");
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");

            Assert.Contains("void HandleCapabilities(const httplib::Request& req, httplib::Response& res);", header);
            Assert.Contains("m_server->Get(\"/capabilities\"", source);
            Assert.Contains("HandleCapabilities(req, res);", source);
            Assert.DoesNotContain("RookRegisterCapabilitiesServer", source);
        }

        [Fact]
        public void CapabilityDocument_ContainsRequiredDomainsAndSchemaFields()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");

            Assert.Contains("BuildRookCapabilitiesDocument", source);
            Assert.Contains("\"schemaVersion\"", source);
            Assert.Contains("\"generatedUtc\"", source);
            Assert.Contains("\"domains\"", source);
            Assert.Contains("\"domainId\"", source);
            Assert.Contains("\"declared\"", source);
            Assert.Contains("\"installed\"", source);
            Assert.Contains("\"state\"", source);
            Assert.Contains("\"stateSource\"", source);
            Assert.Contains("\"reasonCode\"", source);
            Assert.Contains("\"evidence\"", source);

            foreach (var domain in RequiredDomains)
            {
                Assert.Contains(domain, source);
            }
        }

        [Fact]
        public void Discovery_KeepsLegacyGhCapabilityFieldsAndAddsDomainSummary()
        {
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var writeDiscovery = ExtractFunction(source, "CRookServer::WriteDiscoveryFile");

            Assert.Contains("\"ghProvider\"", writeDiscovery);
            Assert.Contains("\"ghRoutes\"", writeDiscovery);
            Assert.Contains("\"domainSummary\"", writeDiscovery);
            Assert.Contains("BuildCompactCapabilitySummary", writeDiscovery);
        }

        [Fact]
        public void BridgeEvidence_IsGranularByDomain()
        {
            var header = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.h");
            var serverSource = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var capabilityBuilder = ExtractFunction(serverSource, "BuildRookCapabilitiesDocument");

            Assert.Contains("bool HasGrasshopperCoreRegistration();", header);
            Assert.Contains("bool HasVisionDispatchRegistration();", header);
            Assert.Contains("bool HasBimDispatchRegistration();", header);
            Assert.Contains("bool HasViewportCaptureTier3Registration();", header);
            Assert.Contains("bool HasBlockDefinitionMutationRegistration();", header);

            Assert.Contains("HasGrasshopperCoreRegistration()", capabilityBuilder);
            Assert.Contains("HasVisionDispatchRegistration()", capabilityBuilder);
            Assert.Contains("HasBimDispatchRegistration()", capabilityBuilder);
            Assert.Contains("HasViewportCaptureTier3Registration()", capabilityBuilder);
            Assert.Contains("HasBlockDefinitionMutationRegistration()", capabilityBuilder);
            Assert.DoesNotContain("HasGrasshopperBridgeRegistration()", capabilityBuilder);
        }

        [Fact]
        public void CapabilityPhase_DoesNotChangeCompanionLoadingOrInstallerLayout()
        {
            var nativePlugin = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var installer = ReadSourceFile("installer", "RookSetup.iss");
            var deploy = ReadSourceFile("scripts", "deploy-local-testing.ps1");

            Assert.Contains("StartCompanionLoadDeferred();", nativePlugin);
            Assert.DoesNotContain("installed-modules.json", installer);
            Assert.DoesNotContain("installed-modules.json", deploy);
        }

        private static string ExtractFunction(string source, string functionName)
        {
            var signatureStart = source.IndexOf(functionName + "(", StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Function not found: " + functionName);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Function body not found: " + functionName);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(signatureStart, i - signatureStart + 1);
                }
            }

            throw new InvalidOperationException("Function body did not close: " + functionName);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);
                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
```

- [ ] **Step 2: Run the failing source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~CapabilityDiscoverySourceTests
```

Expected: FAIL. The failure must include missing `HandleCapabilities`, missing `BuildRookCapabilitiesDocument`, or missing granular bridge helper declarations.

- [ ] **Step 3: Commit the failing tests**

Run:

```powershell
git add src/Rook.Tests/Capabilities/CapabilityDiscoverySourceTests.cs
git commit -m "test: pin phase 1 capability discovery contract"
```

Expected: commit succeeds.

## Task 2: Granular Native Bridge Evidence Helpers

**Files:**

- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.h`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`

- [ ] **Step 1: Add granular helper declarations**

In `src/RookNative/Handlers/GrasshopperProxyHandler.h`, keep `HasGrasshopperBridgeRegistration()` and add these declarations immediately below it:

```cpp
bool HasGrasshopperCoreRegistration();
bool HasVisionDispatchRegistration();
bool HasBimDispatchRegistration();
bool HasViewportCaptureTier3Registration();
bool HasBlockDefinitionMutationRegistration();
```

- [ ] **Step 2: Add granular helper implementation**

In `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`, replace the existing `HasGhBridgeRegistration()` body with helper functions that keep the old broad behavior intact while exposing per-domain probes:

```cpp
bool HasGrasshopperCoreRegistrationLocked(const GhBridgeRegistration& registration)
{
    return registration.version == kGhBridgeAbiVersion
        && registration.gh_status != nullptr
        && registration.gh_document != nullptr
        && registration.gh_query != nullptr
        && registration.gh_selection != nullptr
        && registration.gh_categories != nullptr
        && registration.gh_library != nullptr
        && registration.gh_get_value != nullptr
        && registration.gh_connections != nullptr
        && registration.gh_groups != nullptr
        && registration.gh_component != nullptr
        && registration.gh_inspect_output != nullptr
        && registration.gh_errors != nullptr
        && registration.gh_get_reference != nullptr
        && registration.gh_set_script != nullptr
        && registration.gh_preview != nullptr
        && registration.gh_clear != nullptr
        && registration.gh_open_document != nullptr
        && registration.gh_new_document != nullptr
        && registration.gh_set_reference != nullptr
        && registration.gh_clear_reference != nullptr
        && registration.gh_move != nullptr
        && registration.gh_group != nullptr
        && registration.gh_group_resize != nullptr
        && registration.gh_cluster != nullptr
        && registration.gh_explore_selection != nullptr
        && registration.gh_explore_cluster != nullptr
        && registration.gh_batch_component_info != nullptr
        && registration.gh_create_component != nullptr
        && registration.gh_create_slider != nullptr
        && registration.gh_create_panel != nullptr
        && registration.gh_connect != nullptr
        && registration.gh_disconnect != nullptr
        && registration.gh_set_value != nullptr
        && registration.gh_delete != nullptr
        && registration.gh_solve != nullptr
        && registration.gh_bake_output != nullptr;
}

bool HasBlockDefinitionMutationRegistrationLocked(const GhBridgeRegistration& registration)
{
    return registration.version == kGhBridgeAbiVersion
        && registration.block_set_layers != nullptr
        && registration.block_set_materials != nullptr
        && registration.block_set_object_colors != nullptr
        && registration.block_set_object_names != nullptr
        && registration.block_set_object_user_strings != nullptr
        && registration.block_replace_object_geometry != nullptr
        && registration.block_transform_object != nullptr;
}

bool HasGhBridgeRegistration()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    const auto& registration = g_ghBridgeRegistration;
    return HasGrasshopperCoreRegistrationLocked(registration)
        && registration.vision_dispatch != nullptr
        && registration.bim_dispatch != nullptr;
}
```

Then add the public helper definitions near `HasGrasshopperBridgeRegistration()`:

```cpp
bool HasGrasshopperCoreRegistration()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    return HasGrasshopperCoreRegistrationLocked(g_ghBridgeRegistration);
}

bool HasVisionDispatchRegistration()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    return g_ghBridgeRegistration.version == kGhBridgeAbiVersion
        && g_ghBridgeRegistration.vision_dispatch != nullptr;
}

bool HasBimDispatchRegistration()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    return g_ghBridgeRegistration.version == kGhBridgeAbiVersion
        && g_ghBridgeRegistration.bim_dispatch != nullptr;
}

bool HasViewportCaptureTier3Registration()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    return g_ghBridgeRegistration.version == kGhBridgeAbiVersion
        && g_ghBridgeRegistration.viewport_capture_tier3 != nullptr;
}

bool HasBlockDefinitionMutationRegistration()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    return HasBlockDefinitionMutationRegistrationLocked(g_ghBridgeRegistration);
}
```

- [ ] **Step 3: Run the focused source test**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CapabilityDiscoverySourceTests.BridgeEvidence_IsGranularByDomain"
```

Expected: FAIL only because `BuildRookCapabilitiesDocument` is not implemented yet. The helper declarations and definitions should now be found.

- [ ] **Step 4: Commit granular helpers**

Run:

```powershell
git add src/RookNative/Handlers/GrasshopperProxyHandler.h src/RookNative/Handlers/GrasshopperProxyHandler.cpp
git commit -m "feat: expose granular native bridge evidence probes"
```

Expected: commit succeeds.

## Task 3: Native `/capabilities` Route And Discovery Summary

**Files:**

- Modify: `src/RookNative/RookServer.h`
- Modify: `src/RookNative/RookServer.cpp`

- [ ] **Step 1: Add the route handler declaration**

In `src/RookNative/RookServer.h`, add this declaration immediately below `HandlePing`:

```cpp
void HandleCapabilities(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 2: Add capability helper functions in `RookServer.cpp`**

In `src/RookNative/RookServer.cpp`, add these helpers inside the existing anonymous namespace immediately after the existing `GetNativeGrasshopperRoutes()` definition and before `CRookServer::WriteDiscoveryFile()`.

Do not place these helpers before `CRookServer::RegisterRoutes()`. `BuildRookCapabilitiesDocument()` calls `GetNativeGrasshopperRoutes()`, and the helper must be defined after that function unless a separate forward declaration is added. This plan uses placement after `GetNativeGrasshopperRoutes()` to avoid extra declarations.

```cpp
nlohmann::json MakeCapabilityEvidence(
    const std::string& kind,
    const std::string& name,
    const nlohmann::json& value)
{
    return {
        {"kind", kind},
        {"name", name},
        {"value", value}
    };
}

std::string MakeUtcTimestamp()
{
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    std::ostringstream ts;
    struct tm tm_buf = {};
    if (gmtime_s(&tm_buf, &time) == 0)
    {
        ts << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%SZ");
    }
    else
    {
        ts << time;
    }
    return ts.str();
}

nlohmann::json MakeCapabilityDomain(
    const std::string& domainId,
    const std::string& installed,
    bool loaded,
    const std::string& state,
    bool ready,
    const std::string& reasonCode,
    bool retryable,
    const std::string& stateSource,
    const std::string& message,
    const nlohmann::json& routes,
    const nlohmann::json& operations,
    const nlohmann::json& diagnostics,
    const nlohmann::json& evidence)
{
    return {
        {"domainId", domainId},
        {"declared", true},
        {"installed", installed},
        {"loaded", loaded},
        {"state", state},
        {"ready", ready},
        {"reasonCode", reasonCode},
        {"retryable", retryable},
        {"stateSource", stateSource},
        {"message", message},
        {"routes", routes},
        {"operations", operations},
        {"diagnostics", diagnostics},
        {"evidence", evidence}
    };
}

nlohmann::json ReadCompanionRuntimeStatus(const DiscoveryRootInfo& rootInfo, DWORD pid)
{
    const fs::path statusPath = rootInfo.sharedDiscoveryFolder
        / ("companion-" + std::to_string(pid) + ".json");
    if (!fs::exists(statusPath))
    {
        return nlohmann::json::object();
    }

    try
    {
        std::ifstream file(statusPath);
        if (!file.is_open())
            return nlohmann::json::object();

        nlohmann::json status;
        file >> status;
        if (!status.is_object())
            return nlohmann::json::object();
        return status;
    }
    catch (...)
    {
        return nlohmann::json::object();
    }
}

nlohmann::json MakeManagedDependencyDomain(
    const std::string& domainId,
    bool callbackRegistered,
    const std::string& callbackName,
    const nlohmann::json& routes,
    const nlohmann::json& operations,
    const nlohmann::json& diagnostics)
{
    if (callbackRegistered)
    {
        return MakeCapabilityDomain(
            domainId,
            "unknown",
            true,
            "unknown",
            false,
            "operation_state_not_probed_phase1",
            true,
            "native_bridge_callback_registration",
            "The native callback surface for this domain is registered. Phase 1 does not probe provider or operation health inside this endpoint.",
            routes,
            operations,
            diagnostics,
            nlohmann::json::array({
                MakeCapabilityEvidence("callback", callbackName, true)
            }));
    }

    return MakeCapabilityDomain(
        domainId,
        "unknown",
        false,
        "not_loaded",
        false,
        "managed_bridge_callback_not_registered",
        true,
        "native_bridge_callback_registration",
        "This managed-backed domain is declared, but its native callback slot is not registered.",
        routes,
        operations,
        diagnostics,
        nlohmann::json::array({
            MakeCapabilityEvidence("callback", callbackName, false)
        }));
}

void MergeCompanionCapabilityEvidence(
    nlohmann::json& domains,
    const nlohmann::json& companionStatus)
{
    if (!companionStatus.contains("capabilityDomains") || !companionStatus["capabilityDomains"].is_array())
        return;

    for (auto& domain : domains)
    {
        if (!domain.is_object() || !domain.contains("domainId"))
            continue;

        const std::string domainId = domain.value("domainId", "");
        for (const auto& companionDomain : companionStatus["capabilityDomains"])
        {
            if (!companionDomain.is_object())
                continue;

            if (companionDomain.value("domainId", "") == domainId)
            {
                domain["companionEvidence"] = companionDomain;
                break;
            }
        }
    }
}

nlohmann::json BuildRookCapabilitiesDocument(
    int port,
    const DiscoveryRootInfo& rootInfo,
    const nlohmann::json& companionStatus)
{
    const DWORD pid = ::GetCurrentProcessId();
    const bool rhinoInside = CRookNativePlugin::IsRhinoInside();
    const bool ghCoreReady = Rook::Handlers::HasGrasshopperCoreRegistration();
    const bool visionReady = Rook::Handlers::HasVisionDispatchRegistration();
    const bool bimDispatchReady = Rook::Handlers::HasBimDispatchRegistration();
    const bool tier3CaptureReady = Rook::Handlers::HasViewportCaptureTier3Registration();
    const bool blockMutationReady = Rook::Handlers::HasBlockDefinitionMutationRegistration();

    nlohmann::json domains = nlohmann::json::array();

    domains.push_back(MakeCapabilityDomain(
        "native.core",
        "present",
        true,
        "ready",
        true,
        "native_server_running",
        false,
        "native_server_runtime",
        "RookNative is loaded, the HTTP server is running, and native discovery is being written.",
        nlohmann::json::array({"GET /ping", "GET /capabilities"}),
        nlohmann::json::array({"ping", "capability_discovery"}),
        nlohmann::json::array({"GET /ping", "native discovery file"}),
        nlohmann::json::array({
            MakeCapabilityEvidence("http", "port", port),
            MakeCapabilityEvidence("process", "processId", static_cast<int>(pid)),
            MakeCapabilityEvidence("discovery", "root", PathToUtf8String(rootInfo.sharedDiscoveryFolder))
        })));

    domains.push_back(MakeCapabilityDomain(
        "native.command_control",
        "present",
        true,
        "ready",
        true,
        "native_routes_registered",
        false,
        "native_route_registration",
        "Command prompt, send, and cancel routes are native command-control routes. Command start remains normal dispatch.",
        nlohmann::json::array({"GET /command/prompt", "POST /command/send", "POST /command/cancel", "POST /command/start"}),
        nlohmann::json::array({"prompt", "send", "cancel", "start"}),
        nlohmann::json::array({"GET /command/prompt"}),
        nlohmann::json::array({
            MakeCapabilityEvidence("route", "commandPrompt", true),
            MakeCapabilityEvidence("route", "commandSend", true),
            MakeCapabilityEvidence("route", "commandCancel", true),
            MakeCapabilityEvidence("route", "commandStartNormalDispatch", true)
        })));

    domains.push_back(MakeCapabilityDomain(
        "gh.bridge",
        "unknown",
        ghCoreReady,
        ghCoreReady ? "ready" : "not_loaded",
        ghCoreReady,
        ghCoreReady ? "grasshopper_core_callbacks_registered" : "grasshopper_core_callbacks_not_registered",
        !ghCoreReady,
        "native_bridge_callback_registration",
        ghCoreReady
            ? "Grasshopper core callback slots are registered."
            : "Grasshopper bridge exists as a declared domain, but core callback slots are not registered yet.",
        GetNativeGrasshopperRoutes(),
        nlohmann::json::array({"status", "document", "query", "mutate"}),
        nlohmann::json::array({"GET /gh/status"}),
        nlohmann::json::array({
            MakeCapabilityEvidence("callback", "grasshopperCore", ghCoreReady)
        })));

    domains.push_back(MakeCapabilityDomain(
        "gh.canvas",
        "unknown",
        ghCoreReady,
        ghCoreReady ? "unknown" : "not_loaded",
        false,
        ghCoreReady ? "canvas_state_requires_gh_status" : "grasshopper_core_callbacks_not_registered",
        true,
        "gh_status_route",
        "Active Grasshopper canvas readiness is discovered through /gh/status; Phase 1 does not infer canvas readiness from bridge registration.",
        nlohmann::json::array({"GET /gh/status", "GET /gh/document", "GET /gh/query"}),
        nlohmann::json::array({"canvas_status", "canvas_query", "canvas_mutation"}),
        nlohmann::json::array({"GET /gh/status"}),
        nlohmann::json::array({
            MakeCapabilityEvidence("callback", "grasshopperCore", ghCoreReady),
            MakeCapabilityEvidence("callback", "canvasGraphProtocol", Rook::Handlers::HasCanvasGraphProtocol()),
            MakeCapabilityEvidence("callback", "canvasGraphNavigation", Rook::Handlers::HasCanvasGraphNavigation())
        })));

    domains.push_back(MakeCapabilityDomain(
        "bim.rhino_inside_revit",
        "unknown",
        bimDispatchReady,
        !bimDispatchReady ? "not_loaded" : (rhinoInside ? "unknown" : "blocked_by_host"),
        false,
        !bimDispatchReady ? "bim_dispatch_callback_not_registered" : (rhinoInside ? "bim_status_not_probed_phase1" : "not_rhino_inside"),
        rhinoInside,
        !bimDispatchReady ? "native_bridge_callback_registration" : "native_host_state",
        !bimDispatchReady
            ? "RookBIM is declared, but the BIM dispatch callback is not registered."
            : (rhinoInside
                ? "RookBIM dispatch is registered in a Rhino.Inside host; use /bim/status for operation readiness."
                : "RookBIM is declared, but this Rhino process is not hosted inside Revit."),
        nlohmann::json::array({"GET /bim/status", "GET /bim/active-document", "GET /bim/categories", "POST /bim/query-elements"}),
        nlohmann::json::array({"status", "active_document", "list_categories", "query_elements"}),
        nlohmann::json::array({"GET /bim/status"}),
        nlohmann::json::array({
            MakeCapabilityEvidence("callback", "bimDispatch", bimDispatchReady),
            MakeCapabilityEvidence("host", "rhinoInside", rhinoInside)
        })));

    domains.push_back(MakeManagedDependencyDomain(
        "vision.media",
        visionReady,
        "visionDispatch",
        nlohmann::json::array({"POST /vision/generate", "POST /vision/enhance-prompt", "GET /vision/artifacts", "POST /vision/video/jobs"}),
        nlohmann::json::array({"image_generation", "prompt_enhancement", "artifact_store", "video_jobs"}),
        nlohmann::json::array({"vision route responses", "companion runtime status"})));

    domains.push_back(MakeManagedDependencyDomain(
        "viewport.capture",
        tier3CaptureReady,
        "viewportCaptureTier3",
        nlohmann::json::array({"POST /viewport"}),
        nlohmann::json::array({"viewport_capture"}),
        nlohmann::json::array({"POST /viewport"})));

    domains.push_back(MakeManagedDependencyDomain(
        "block.definition_mutation",
        blockMutationReady,
        "blockDefinitionMutation",
        nlohmann::json::array({"POST /block/set-layers", "POST /block/set-materials", "POST /block/set-object-colors", "POST /block/set-object-names", "POST /block/set-object-user-strings", "POST /block/replace-object-geometry", "POST /block/transform-object"}),
        nlohmann::json::array({"set_layers", "set_materials", "set_object_colors", "set_object_names", "set_object_user_strings", "replace_object_geometry", "transform_object"}),
        nlohmann::json::array({"companion runtime status"})));

    domains.push_back(MakeCapabilityDomain(
        "chat.ui",
        "unknown",
        companionStatus.value("startupComplete", false),
        companionStatus.value("startupComplete", false) ? "unknown" : "not_loaded",
        false,
        companionStatus.value("startupComplete", false) ? "chat_service_state_not_probed_phase1" : "companion_startup_not_complete",
        true,
        "companion_runtime_status_file",
        "Chat UI is a managed companion domain. Phase 1 reports companion startup evidence without probing chat service health.",
        nlohmann::json::array(),
        nlohmann::json::array({"panel_registration", "chat_service"}),
        nlohmann::json::array({"companion runtime status", "chat service manifest"}),
        nlohmann::json::array({
            MakeCapabilityEvidence("statusFile", "present", companionStatus.is_object() && !companionStatus.empty()),
            MakeCapabilityEvidence("companion", "startupComplete", companionStatus.value("startupComplete", false))
        })));

    domains.push_back(MakeCapabilityDomain(
        "mcp.runtime",
        "unknown",
        false,
        "unknown",
        false,
        "install_evidence_not_available_phase1",
        false,
        "explicit_phase1_unavailable_provider",
        "MCP runtime is declared for client discoverability, but Phase 1 does not introduce installer module manifests or runtime/install correlation.",
        nlohmann::json::array(),
        nlohmann::json::array({"client_runtime"}),
        nlohmann::json::array({"rook doctor", "MCP client configuration"}),
        nlohmann::json::array()));

    domains.push_back(MakeCapabilityDomain(
        "knowledge.stores",
        "unknown",
        false,
        "unknown",
        false,
        "install_evidence_not_available_phase1",
        false,
        "explicit_phase1_unavailable_provider",
        "Knowledge stores are declared for client discoverability; install evidence arrives in a later phase.",
        nlohmann::json::array(),
        nlohmann::json::array({"knowledge_lookup"}),
        nlohmann::json::array({"rook doctor"}),
        nlohmann::json::array()));

    domains.push_back(MakeCapabilityDomain(
        "chirp.runtime",
        "unknown",
        false,
        "unknown",
        false,
        "install_evidence_not_available_phase1",
        false,
        "explicit_phase1_unavailable_provider",
        "Chirp runtime is declared for client discoverability; install evidence arrives in a later phase.",
        nlohmann::json::array(),
        nlohmann::json::array({"chirp_component_runtime"}),
        nlohmann::json::array({"Chirp service discovery"}),
        nlohmann::json::array()));

    domains.push_back(MakeCapabilityDomain(
        "licensing.entitlement",
        "reserved",
        false,
        "reserved",
        false,
        "future_domain_reserved",
        false,
        "explicit_unavailable_provider",
        "Licensing and entitlement state is reserved as a future discoverable domain.",
        nlohmann::json::array(),
        nlohmann::json::array({"license_state"}),
        nlohmann::json::array(),
        nlohmann::json::array()));

    MergeCompanionCapabilityEvidence(domains, companionStatus);

    nlohmann::json document;
    document["schemaVersion"] = 1;
    document["generatedUtc"] = MakeUtcTimestamp();
    document["source"] = "RookNative";
    document["processId"] = static_cast<int>(pid);
    document["pluginType"] = "native";
    document["pluginVersion"] = "1.5.9";
    document["rhinoInside"] = rhinoInside;
    document["domains"] = domains;
    return document;
}

nlohmann::json BuildCompactCapabilitySummary(const nlohmann::json& capabilityDocument)
{
    nlohmann::json summary = nlohmann::json::array();
    const auto& domains = capabilityDocument.value("domains", nlohmann::json::array());
    for (const auto& domain : domains)
    {
        if (!domain.is_object() || !domain.contains("domainId"))
            continue;

        summary.push_back({
            {"domainId", domain.value("domainId", "")},
            {"state", domain.value("state", "unknown")},
            {"ready", domain.value("ready", false)},
            {"reasonCode", domain.value("reasonCode", "unknown")}
        });
    }

    return summary;
}
```

- [ ] **Step 3: Register `GET /capabilities`**

In `CRookServer::RegisterRoutes()`, immediately after `/ping`, add:

```cpp
m_server->Get("/capabilities", [this](const httplib::Request& req, httplib::Response& res) {
    HandleCapabilities(req, res);
});
```

- [ ] **Step 4: Implement the route handler**

In `src/RookNative/RookServer.cpp`, add this member function after the capability helpers from Step 2 and before `CRookServer::WriteDiscoveryFile()`:

```cpp
void CRookServer::HandleCapabilities(const httplib::Request& /*req*/, httplib::Response& res)
{
    const DiscoveryRootInfo rootInfo = ResolveDiscoveryRootInfo();
    const auto companionStatus = ReadCompanionRuntimeStatus(rootInfo, ::GetCurrentProcessId());
    const auto document = BuildRookCapabilitiesDocument(m_port, rootInfo, companionStatus);
    res.status = 200;
    res.set_content(document.dump(), "application/json");
}
```

`/capabilities` intentionally returns the capability document directly, not the standard `{ "success": true, "data": ... }` envelope. This keeps `schemaVersion`, `generatedUtc`, and `domains` at the top level for schema/discovery consumers.

- [ ] **Step 5: Add the compact summary to discovery without removing legacy fields**

In `CRookServer::WriteDiscoveryFile()`, replace the current `info["capabilities"] = ...` assignment with:

```cpp
const auto ghRoutes = GetNativeGrasshopperRoutes();
const bool callbackBridgeReady = Rook::Handlers::HasGrasshopperBridgeRegistration();
const auto companionStatus = ReadCompanionRuntimeStatus(rootInfo, pid);
const auto capabilityDocument = BuildRookCapabilitiesDocument(m_port, rootInfo, companionStatus);
info["capabilities"] = {
    {"ghProvider", "callback"},
    {"ghRoutes", callbackBridgeReady ? ghRoutes : nlohmann::json::array()},
    {"schemaVersion", capabilityDocument.value("schemaVersion", 1)},
    {"liveEndpoint", "/capabilities"},
    {"summaryKind", "bootstrap_snapshot"},
    {"authoritative", false},
    {"generatedUtc", MakeUtcTimestamp()},
    {"domainSummary", BuildCompactCapabilitySummary(capabilityDocument)}
};
```

- [ ] **Step 6: Run focused source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~CapabilityDiscoverySourceTests
```

Expected: PASS for the source tests added in Task 1.

- [ ] **Step 7: Commit native capability route**

Run:

```powershell
git add src/RookNative/RookServer.h src/RookNative/RookServer.cpp
git commit -m "feat: expose native capability discovery"
```

Expected: commit succeeds.

## Task 4: Managed Companion Domain Status Evidence

**Files:**

- Create: `src/Rook/Capabilities/CapabilityDomainStatus.cs`
- Modify: `src/Rook/Startup/CompanionRuntimeStatus.cs`
- Modify: `src/Rook/RookPlugin.cs`
- Modify: `src/Rook.Tests/Plugin/CompanionRuntimeStatusTests.cs`

- [ ] **Step 1: Add managed tests for companion status JSON**

Modify `src/Rook.Tests/Plugin/CompanionRuntimeStatusTests.cs`.

First, add the missing namespace import at the top of the file:

```csharp
using Rook.Capabilities;
```

Then, in the snapshot construction inside `BuildJson_IncludesRuntimeSelfReportFields`, add `PanelsRegistered: true` and assert the new JSON fields:

```csharp
var snapshot = new CompanionRuntimeStatusSnapshot(
    ProcessId: 1234,
    ProcessName: "Revit",
    RhinoInside: true,
    AssemblyLocation: @"C:\Users\a\AppData\Roaming\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rhp",
    TargetFramework: ".NETFramework,Version=v4.8",
    StartupGateAttached: true,
    DeferredLocalStartupComplete: true,
    StartupComplete: true,
    BridgeRegistered: true,
    PanelsRegistered: true,
    OnLoadUtc: onLoadUtc,
    StartupCompleteUtc: startupCompleteUtc,
    CapabilityDomains: CapabilityDomainStatusBuilder.BuildCompanionDomains(
        rhinoInside: true,
        startupComplete: true,
        bridgeRegistered: true,
        panelsRegistered: true));
```

Add these assertions after the existing `bridgeRegistered` assertion:

```csharp
Assert.True(root.GetProperty("panelsRegistered").GetBoolean());
var domains = root.GetProperty("capabilityDomains");
Assert.Equal(JsonValueKind.Array, domains.ValueKind);
Assert.Contains(
    domains.EnumerateArray(),
    domain => domain.GetProperty("domainId").GetString() == "chat.ui"
        && domain.GetProperty("stateSource").GetString() == "managed_companion_runtime");
Assert.Contains(
    domains.EnumerateArray(),
    domain => domain.GetProperty("domainId").GetString() == "bim.rhino_inside_revit"
        && domain.GetProperty("stateSource").GetString() == "managed_rookbim_status_provider");
```

- [ ] **Step 2: Run the failing managed status test**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~CompanionRuntimeStatusTests.BuildJson_IncludesRuntimeSelfReportFields
```

Expected: FAIL because `CapabilityDomainStatusBuilder`, `PanelsRegistered`, and `capabilityDomains` do not exist yet.

- [ ] **Step 3: Add managed capability status records**

Create `src/Rook/Capabilities/CapabilityDomainStatus.cs`:

```csharp
using System;
using System.Collections.Generic;
using Rook.Bim;

namespace Rook.Capabilities
{
    internal sealed record CapabilityEvidence(
        string Kind,
        string Name,
        object? Value);

    internal sealed record CapabilityDomainStatus(
        string DomainId,
        bool Declared,
        string Installed,
        bool Loaded,
        string State,
        bool Ready,
        string ReasonCode,
        bool Retryable,
        string StateSource,
        string Message,
        IReadOnlyList<string> Routes,
        IReadOnlyList<string> Operations,
        IReadOnlyList<string> Diagnostics,
        IReadOnlyList<CapabilityEvidence> Evidence);

    internal static class CapabilityDomainStatusBuilder
    {
        public static IReadOnlyList<CapabilityDomainStatus> BuildCompanionDomains(
            bool rhinoInside,
            bool startupComplete,
            bool bridgeRegistered,
            bool panelsRegistered)
        {
            return new[]
            {
                BuildChatUi(startupComplete, panelsRegistered),
                BuildVisionMedia(bridgeRegistered),
                BuildViewportCapture(bridgeRegistered),
                BuildBlockDefinitionMutation(bridgeRegistered),
                BuildBimRhinoInsideRevit(rhinoInside, bridgeRegistered),
            };
        }

        internal static CapabilityDomainStatus BuildBimRhinoInsideRevit(
            bool rhinoInside,
            bool bridgeRegistered)
        {
            var runtimeStatus = RookBimRuntimeRegistry.Current.Status();
            if (!bridgeRegistered)
            {
                return Domain(
                    "bim.rhino_inside_revit",
                    "unknown",
                    false,
                    "not_loaded",
                    false,
                    "bim_dispatch_callback_not_registered",
                    true,
                    "managed_rookbim_status_provider",
                    "BIM dispatch is not registered through the native bridge.",
                    new[] { "GET /bim/status" },
                    new[] { "status" },
                    new[] { "GET /bim/status" },
                    new[] { Evidence("callback", "bimDispatch", false) });
            }

            if (!rhinoInside || string.Equals(runtimeStatus.ErrorCode, "not_rhino_inside", StringComparison.Ordinal))
            {
                return Domain(
                    "bim.rhino_inside_revit",
                    "unknown",
                    true,
                    "blocked_by_host",
                    false,
                    "not_rhino_inside",
                    false,
                    "managed_rookbim_status_provider",
                    runtimeStatus.Message ?? "RookBIM requires RhinoInside.Revit and RevitAPIUI to be loaded.",
                    new[] { "GET /bim/status" },
                    new[] { "status" },
                    new[] { "GET /bim/status" },
                    new[] { Evidence("host", "rhinoInside", rhinoInside), Evidence("bim", "module", runtimeStatus.Module) });
            }

            return Domain(
                "bim.rhino_inside_revit",
                "unknown",
                string.Equals(runtimeStatus.Runtime, "rookbim", StringComparison.Ordinal),
                runtimeStatus.Available ? "ready" : "unavailable",
                runtimeStatus.Available,
                runtimeStatus.Available ? "rookbim_runtime_available" : (runtimeStatus.ErrorCode ?? "rookbim_runtime_unavailable"),
                !runtimeStatus.Available,
                "managed_rookbim_status_provider",
                runtimeStatus.Available
                    ? "RookBIM runtime reports an available active Revit context."
                    : (runtimeStatus.Message ?? "RookBIM runtime is unavailable."),
                new[] { "GET /bim/status", "GET /bim/active-document", "GET /bim/categories", "POST /bim/query-elements" },
                new[] { "status", "active_document", "list_categories", "query_elements" },
                new[] { "GET /bim/status" },
                new[] { Evidence("bim", "runtime", runtimeStatus.Runtime), Evidence("bim", "module", runtimeStatus.Module) });
        }

        private static CapabilityDomainStatus BuildChatUi(bool startupComplete, bool panelsRegistered)
        {
            return Domain(
                "chat.ui",
                "unknown",
                startupComplete,
                startupComplete && panelsRegistered ? "unknown" : "not_loaded",
                false,
                startupComplete && panelsRegistered ? "chat_service_state_not_probed_phase1" : "companion_ui_not_registered",
                true,
                "managed_companion_runtime",
                "Chat UI is declared and companion-owned. Phase 1 reports panel/startup evidence without probing chat service health.",
                Array.Empty<string>(),
                new[] { "panel_registration", "chat_service" },
                new[] { "companion runtime status" },
                new[] { Evidence("companion", "startupComplete", startupComplete), Evidence("ui", "panelsRegistered", panelsRegistered) });
        }

        private static CapabilityDomainStatus BuildVisionMedia(bool bridgeRegistered)
        {
            return Domain(
                "vision.media",
                "unknown",
                bridgeRegistered,
                bridgeRegistered ? "unknown" : "not_loaded",
                false,
                bridgeRegistered ? "provider_state_not_probed_phase1" : "vision_dispatch_callback_not_registered",
                true,
                "managed_companion_runtime",
                "Vision/media is companion-backed. Phase 1 reports bridge evidence without probing provider credentials or artifact health.",
                new[] { "POST /vision/generate", "POST /vision/enhance-prompt", "GET /vision/artifacts", "POST /vision/video/jobs" },
                new[] { "image_generation", "prompt_enhancement", "artifact_store", "video_jobs" },
                new[] { "vision route responses" },
                new[] { Evidence("callback", "visionDispatch", bridgeRegistered) });
        }

        private static CapabilityDomainStatus BuildViewportCapture(bool bridgeRegistered)
        {
            return Domain(
                "viewport.capture",
                "unknown",
                bridgeRegistered,
                bridgeRegistered ? "unknown" : "not_loaded",
                false,
                bridgeRegistered ? "capture_backend_state_not_probed_phase1" : "viewport_capture_callback_not_registered",
                true,
                "managed_companion_runtime",
                "Viewport capture is declared. Phase 1 reports managed Tier 3 bridge evidence without probing capture backend health.",
                new[] { "POST /viewport" },
                new[] { "viewport_capture" },
                new[] { "POST /viewport" },
                new[] { Evidence("callback", "viewportCaptureTier3", bridgeRegistered) });
        }

        private static CapabilityDomainStatus BuildBlockDefinitionMutation(bool bridgeRegistered)
        {
            return Domain(
                "block.definition_mutation",
                "unknown",
                bridgeRegistered,
                bridgeRegistered ? "unknown" : "not_loaded",
                false,
                bridgeRegistered ? "block_mutation_callback_state_not_probed_phase1" : "block_mutation_callbacks_not_registered",
                true,
                "managed_companion_runtime",
                "Companion-backed block-definition mutation exceptions are declared separately from Grasshopper readiness.",
                new[] { "POST /block/set-layers", "POST /block/set-materials", "POST /block/set-object-colors", "POST /block/set-object-names", "POST /block/set-object-user-strings", "POST /block/replace-object-geometry", "POST /block/transform-object" },
                new[] { "set_layers", "set_materials", "set_object_colors", "set_object_names", "set_object_user_strings", "replace_object_geometry", "transform_object" },
                new[] { "companion runtime status" },
                new[] { Evidence("callback", "blockDefinitionMutation", bridgeRegistered) });
        }

        private static CapabilityEvidence Evidence(string kind, string name, object? value)
        {
            return new CapabilityEvidence(kind, name, value);
        }

        private static CapabilityDomainStatus Domain(
            string domainId,
            string installed,
            bool loaded,
            string state,
            bool ready,
            string reasonCode,
            bool retryable,
            string stateSource,
            string message,
            IReadOnlyList<string> routes,
            IReadOnlyList<string> operations,
            IReadOnlyList<string> diagnostics,
            IReadOnlyList<CapabilityEvidence> evidence)
        {
            return new CapabilityDomainStatus(
                DomainId: domainId,
                Declared: true,
                Installed: installed,
                Loaded: loaded,
                State: state,
                Ready: ready,
                ReasonCode: reasonCode,
                Retryable: retryable,
                StateSource: stateSource,
                Message: message,
                Routes: routes,
                Operations: operations,
                Diagnostics: diagnostics,
                Evidence: evidence);
        }
    }
}
```

- [ ] **Step 4: Extend companion runtime status**

Modify `src/Rook/Startup/CompanionRuntimeStatus.cs`:

1. Add:

```csharp
using System.Collections.Generic;
using Rook.Capabilities;
```

2. Add `PanelsRegistered` and `CapabilityDomains` to the record:

```csharp
internal sealed record CompanionRuntimeStatusSnapshot(
    int ProcessId,
    string ProcessName,
    bool RhinoInside,
    string AssemblyLocation,
    string TargetFramework,
    bool StartupGateAttached,
    bool DeferredLocalStartupComplete,
    bool StartupComplete,
    bool BridgeRegistered,
    bool PanelsRegistered,
    DateTimeOffset OnLoadUtc,
    DateTimeOffset? StartupCompleteUtc,
    IReadOnlyList<CapabilityDomainStatus> CapabilityDomains);
```

3. Add a `panelsRegistered` parameter to `CreateSnapshot` and pass capability domains:

```csharp
public static CompanionRuntimeStatusSnapshot CreateSnapshot(
    bool rhinoInside,
    bool startupGateAttached,
    bool deferredLocalStartupComplete,
    bool startupComplete,
    bool bridgeRegistered,
    bool panelsRegistered,
    DateTimeOffset onLoadUtc,
    DateTimeOffset? startupCompleteUtc)
{
    var process = Process.GetCurrentProcess();
    var assembly = typeof(RookPlugin).Assembly;
    return new CompanionRuntimeStatusSnapshot(
        ProcessId: process.Id,
        ProcessName: process.ProcessName,
        RhinoInside: rhinoInside,
        AssemblyLocation: assembly.Location,
        TargetFramework: ReadTargetFramework(assembly),
        StartupGateAttached: startupGateAttached,
        DeferredLocalStartupComplete: deferredLocalStartupComplete,
        StartupComplete: startupComplete,
        BridgeRegistered: bridgeRegistered,
        PanelsRegistered: panelsRegistered,
        OnLoadUtc: onLoadUtc,
        StartupCompleteUtc: startupCompleteUtc,
        CapabilityDomains: CapabilityDomainStatusBuilder.BuildCompanionDomains(
            rhinoInside,
            startupComplete,
            bridgeRegistered,
            panelsRegistered));
}
```

4. Add fields to `BuildJson`:

```csharp
panelsRegistered = snapshot.PanelsRegistered,
capabilityDomains = snapshot.CapabilityDomains,
```

5. In the `JsonSerializerOptions` used by `BuildJson`, add camel-case serialization so nested capability records emit `domainId`, `stateSource`, and `reasonCode`:

```csharp
return JsonSerializer.Serialize(
    payload,
    new JsonSerializerOptions
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    });
```

- [ ] **Step 5: Track panel-registration evidence in `RookPlugin`**

In `src/Rook/RookPlugin.cs`:

1. Add the field near `_bridgeRegistered`:

```csharp
private bool _panelsRegistered = false;
```

2. In `RegisterStartupPanels()`, after the third `Panels.RegisterPanel(...)` call, set:

```csharp
_panelsRegistered = true;
```

3. In the `catch` block for `RegisterStartupPanels()`, set:

```csharp
_panelsRegistered = false;
```

4. In `WriteCompanionRuntimeStatus()`, pass the value:

```csharp
panelsRegistered: _panelsRegistered,
```

- [ ] **Step 6: Run managed status tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CompanionRuntimeStatusTests"
```

Expected: PASS.

- [ ] **Step 7: Commit managed status evidence**

Run:

```powershell
git add src/Rook/Capabilities/CapabilityDomainStatus.cs src/Rook/Startup/CompanionRuntimeStatus.cs src/Rook/RookPlugin.cs src/Rook.Tests/Plugin/CompanionRuntimeStatusTests.cs
git commit -m "feat: publish managed capability status evidence"
```

Expected: commit succeeds.

## Task 5: BIM Boundary Tests Without Revit References In `src/Rook`

**Files:**

- Create: `src/Rook.Tests/Capabilities/ManagedCapabilityDomainStatusTests.cs`

- [ ] **Step 1: Add managed BIM/domain tests**

Create `src/Rook.Tests/Capabilities/ManagedCapabilityDomainStatusTests.cs`:

```csharp
using System.Linq;
using Rook.Bim;
using Rook.Capabilities;
using Xunit;

namespace Rook.Tests.Capabilities
{
    public class ManagedCapabilityDomainStatusTests
    {
        [Fact]
        public void BimDomain_IsBlockedByHostWhenRuntimeReportsNotRhinoInside()
        {
            try
            {
                RookBimRuntimeRegistry.Install(
                    new RookBimUnavailableRuntime(
                        "not_rhino_inside",
                        "RookBIM requires RhinoInside.Revit and RevitAPIUI to be loaded.",
                        "RookBim.dll"),
                    "RookBim.dll");

                var domain = CapabilityDomainStatusBuilder.BuildBimRhinoInsideRevit(
                    rhinoInside: false,
                    bridgeRegistered: true);

                Assert.Equal("bim.rhino_inside_revit", domain.DomainId);
                Assert.Equal("blocked_by_host", domain.State);
                Assert.Equal("not_rhino_inside", domain.ReasonCode);
                Assert.False(domain.Ready);
                Assert.Equal("managed_rookbim_status_provider", domain.StateSource);
            }
            finally
            {
                RookBimRuntimeRegistry.ResetForTests();
            }
        }

        [Fact]
        public void BimDomain_DoesNotClaimReadyWhenBridgeIsMissing()
        {
            var domain = CapabilityDomainStatusBuilder.BuildBimRhinoInsideRevit(
                rhinoInside: true,
                bridgeRegistered: false);

            Assert.Equal("not_loaded", domain.State);
            Assert.Equal("bim_dispatch_callback_not_registered", domain.ReasonCode);
            Assert.False(domain.Ready);
            Assert.Contains(domain.Evidence, item => item.Name == "bimDispatch");
        }

        [Fact]
        public void CompanionDomainList_KeepsBimSeparateFromGhAndChat()
        {
            var domains = CapabilityDomainStatusBuilder.BuildCompanionDomains(
                rhinoInside: false,
                startupComplete: true,
                bridgeRegistered: true,
                panelsRegistered: true);

            Assert.Contains(domains, domain => domain.DomainId == "bim.rhino_inside_revit");
            Assert.Contains(domains, domain => domain.DomainId == "chat.ui");
            Assert.Contains(domains, domain => domain.DomainId == "vision.media");
            Assert.DoesNotContain(domains, domain => domain.DomainId == "gh.bridge");
        }

        [Fact]
        public void ManagedCapabilityCode_DoesNotReferenceAutodeskOrRevitApi()
        {
            var source = ReadSourceFile("src", "Rook", "Capabilities", "CapabilityDomainStatus.cs");

            Assert.DoesNotContain("Autodesk", source);
            Assert.DoesNotContain("RevitAPI", source);
            Assert.DoesNotContain("RhinoInside.Revit", source);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new System.IO.DirectoryInfo(System.AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = System.IO.Path.Combine(dir.FullName, System.IO.Path.Combine(pathParts));
                if (System.IO.File.Exists(candidate))
                    return System.IO.File.ReadAllText(candidate);
                dir = dir.Parent;
            }

            throw new System.IO.FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
```

- [ ] **Step 2: Run focused BIM capability tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~ManagedCapabilityDomainStatusTests
```

Expected: PASS.

- [ ] **Step 3: Commit BIM boundary tests**

Run:

```powershell
git add src/Rook.Tests/Capabilities/ManagedCapabilityDomainStatusTests.cs
git commit -m "test: pin managed capability domain boundaries"
```

Expected: commit succeeds.

## Task 6: MCP Discovery Normalization And Live Capability Resolution

**Files:**

- Modify: `mcp_server/src/rook/bridge.py`
- Modify: `mcp_server/tests/test_bridge.py`

- [ ] **Step 1: Add failing MCP tests**

Append these tests to `mcp_server/tests/test_bridge.py`:

```python
def test_normalize_instance_preserves_capability_domains() -> None:
    raw = {
        "host": "127.0.0.1",
        "port": 9950,
        "processId": 7101,
        "pluginType": "native",
        "capabilities": {
            "schemaVersion": 1,
            "ghProvider": "callback",
            "ghRoutes": [],
            "domainSummary": [
                {
                    "domainId": "bim.rhino_inside_revit",
                    "state": "blocked_by_host",
                    "ready": False,
                    "reasonCode": "not_rhino_inside",
                }
            ],
        },
    }

    normalized = bridge._normalize_instance(raw)

    assert normalized["capabilities"]["schemaVersion"] == 1
    assert normalized["capabilities"]["domainSummary"] == [
        {
            "domainId": "bim.rhino_inside_revit",
            "state": "blocked_by_host",
            "ready": False,
            "reasonCode": "not_rhino_inside",
        }
    ]


def test_get_bootstrap_capability_domain_summary_returns_matching_domain() -> None:
    instance = {
        "capabilities": {
            "domainSummary": [
                {"domainId": "native.core", "state": "ready", "ready": True},
                {"domainId": "bim.rhino_inside_revit", "state": "blocked_by_host", "ready": False},
            ]
        }
    }

    domain = bridge.get_bootstrap_capability_domain_summary(instance, "bim.rhino_inside_revit")

    assert domain == {
        "domainId": "bim.rhino_inside_revit",
        "state": "blocked_by_host",
        "ready": False,
    }


def test_get_bootstrap_capability_domain_summary_handles_older_discovery() -> None:
    instance = {"capabilities": {"ghProvider": "callback", "ghRoutes": []}}

    assert bridge.get_bootstrap_capability_domain_summary(instance, "native.core") is None


```

Also add async tests proving:

- `resolve_capabilities(instance)` returns live `/capabilities` data when the
  live endpoint is reachable, even if `domainSummary` has stale state.
- `resolve_capabilities(instance)` falls back to discovery metadata only when
  the live endpoint fails, and the fallback result is marked
  `source: "discovery_bootstrap_fallback"`, `stale: true`, and
  `authoritative: false`.

- [ ] **Step 2: Run failing MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bridge.py -k "capability_domain" -q
```

Expected: FAIL because live capability resolution helpers do not exist.

- [ ] **Step 3: Add MCP helpers**

In `mcp_server/src/rook/bridge.py`, add helpers immediately after `_normalize_instance`:

```python
def get_bootstrap_capability_domain_summary(
    instance: dict[str, Any],
    domain_id: str,
) -> dict[str, Any] | None:
    """Return a bootstrap capability domain summary from native discovery.

    This is stale/non-authoritative bootstrap metadata. Older discovery files
    do not have domainSummary. This helper returns None for those files so
    callers can remain backward compatible.
    """
    capabilities = instance.get("capabilities") or {}
    domains = capabilities.get("domainSummary") or []
    if not isinstance(domains, list):
        return None

    for domain in domains:
        if isinstance(domain, dict) and domain.get("domainId") == domain_id:
            return domain

    return None


```

MCP must use discovery to locate Rook and `GET /capabilities` to understand
current readiness. `capabilities.domainSummary` is only bootstrap/fallback
metadata and must be marked stale/non-authoritative when used after a live
capabilities request fails.

Add `resolve_capabilities(instance, timeout=None)` to return an envelope with
`source`, `stale`, `authoritative`, `liveEndpoint`, and `capabilities`. Add
`get_resolved_capability_domain(resolved, domain_id)` to read a domain from
live `domains` first and bootstrap `domainSummary` only as fallback.

- [ ] **Step 4: Run MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bridge.py -k "capability_domain or rhino_inside_native_record" -q
```

Expected: PASS.

- [ ] **Step 5: Commit MCP normalization**

Run:

```powershell
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_bridge.py
git commit -m "feat: preserve capability domain discovery in MCP"
```

Expected: commit succeeds.

## Task 7: Documentation And Cross-Phase Guardrails

**Files:**

- Modify: `docs/CURRENT_ARCHITECTURE.md`

- [ ] **Step 1: Update the current architecture doc**

In `docs/CURRENT_ARCHITECTURE.md`, add a short section near the native discovery discussion:

```markdown
## Runtime Capability Discovery

RookNative exposes `GET /capabilities` as the public runtime capability discovery surface. The endpoint reports declared capability domains, current runtime state, reason codes, routes, operations, diagnostics, and evidence. It is descriptive in Phase 1: it does not move route ownership, change companion loading, change installer layout, or make managed companion public.

Native discovery JSON keeps the legacy `capabilities.ghProvider` and `capabilities.ghRoutes` fields for compatibility. It also includes `capabilities.liveEndpoint`, `capabilities.summaryKind: "bootstrap_snapshot"`, `capabilities.authoritative: false`, `capabilities.generatedUtc`, and `capabilities.domainSummary`. This summary is bootstrap/fallback metadata only. Clients should use discovery to find Rook, then call `GET /capabilities` for authoritative live readiness.

Managed companion domain evidence is internal. The companion writes it to its existing per-process runtime status file under the shared discovery root; RookNative remains the only public HTTP/discovery surface.
```

- [ ] **Step 2: Run docs/source guard tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CapabilityDiscoverySourceTests|FullyQualifiedName~CompanionRuntimeStatusTests|FullyQualifiedName~ManagedCapabilityDomainStatusTests"
```

Expected: PASS.

- [ ] **Step 3: Commit documentation**

Run:

```powershell
git add docs/CURRENT_ARCHITECTURE.md
git commit -m "docs: document phase 1 capability discovery surface"
```

Expected: commit succeeds.

## Task 8: Static, Managed, MCP, Native Build, And Live Validation

**Files:**

- No planned file changes.

- [ ] **Step 1: Run focused managed/source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CapabilityDiscoverySourceTests|FullyQualifiedName~CompanionRuntimeStatusTests|FullyQualifiedName~ManagedCapabilityDomainStatusTests"
```

Expected: PASS.

- [ ] **Step 2: Run focused MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_bridge.py -k "capability_domain or rhino_inside_native_record" -q
```

Expected: PASS.

- [ ] **Step 3: Run native MSVC build with the known working toolset**

Run:

```powershell
cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds. If the machine lacks the Rhino/MFC toolchain, record the exact missing toolchain error and do not claim native build verification.

- [ ] **Step 4: Run whitespace check**

Run:

```powershell
git diff --check origin/main...HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 5: Deploy locally for live validation**

Run the existing local deploy workflow:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1
```

Expected: deploy completes without errors and updates the installed Rook runtime.

- [ ] **Step 6: Live validate `/capabilities` in standalone Rhino**

Open Rhino through the local testing flow or normal Rhino launch with the deployed plugin. After RookNative discovery appears, call:

```powershell
$discovery = Get-ChildItem "$env:LOCALAPPDATA\Rook\discovery\instance-*-native.json" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$record = Get-Content $discovery.FullName | ConvertFrom-Json
Invoke-RestMethod "http://127.0.0.1:$($record.port)/capabilities"
```

Expected:

- `schemaVersion` is `1`.
- `domains` contains every required domain ID.
- `native.core` is `ready`.
- `bim.rhino_inside_revit` is discoverable and is not hidden outside Revit.
- Existing discovery still contains `capabilities.ghProvider` and `capabilities.ghRoutes`.
- Discovery metadata includes `capabilities.liveEndpoint: "/capabilities"`,
  `capabilities.summaryKind: "bootstrap_snapshot"`, and
  `capabilities.authoritative: false`.
- MCP live capability resolution reports `source: "live"`, `stale: false`,
  and `authoritative: true` when `/capabilities` is reachable.

- [ ] **Step 7: Live validate no startup regression**

Repeat the recent-file `_Open` startup validation used for the prior native guard work.

Expected:

- Rhino opens the selected recent file without startup deadlock.
- RookNative discovery is written.
- `/ping` responds.
- `/capabilities` responds.
- Companion deferred startup behavior is unchanged.

## Phase 1 Validation Closeout

Recorded on June 1, 2026 after the live-state authority correction:

- Automated managed/source suite:
  `dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CapabilityDiscoverySourceTests|FullyQualifiedName~CompanionRuntimeStatusTests|FullyQualifiedName~ManagedCapabilityDomainStatusTests|FullyQualifiedName~BimHandlerTests"`
  passed 37/37 with existing warnings.
- MCP bridge suite:
  `python -m pytest mcp_server/tests/test_bridge.py -q` passed 54/54.
- Native MSVC build:
  `msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207`
  passed with MSVC 14.44 and the documented `RookServer.cpp` `/bigobj`
  exception.
- Whitespace check:
  `git diff --check origin/main...HEAD` passed.
- Local deploy:
  native plugin rebuilt/deployed to
  `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`; MCP payload synced
  with `-PayloadOnly -AllowRunning`.
- Owned Rhino smoke:
  passed with discovery `summaryKind: "bootstrap_snapshot"`,
  `authoritative: false`, 13 bootstrap domains, and 13 live `/capabilities`
  domains.
- Manual live recent-file startup gate:
  user opened Rhino and loaded a file from the recent-files UI successfully.
  RookVision, RookChat, and RookKnowledge Graph were live.
- Manual live contract smoke against that Rhino instance:
  `/ping` returned `pong`; discovery had `liveEndpoint: "/capabilities"`,
  `summaryKind: "bootstrap_snapshot"`, `authoritative: false`, and 13
  bootstrap domains; live `/capabilities` returned schema version 1 without a
  `{ success, data }` wrapper and 13 live domains; `chat.ui` resolved as
  `state: "unknown"`, `ready: false`,
  `reasonCode: "chat_service_state_not_probed_phase1"`, with two companion
  evidence records; MCP `resolve_capabilities()` returned `source: "live"`,
  `stale: false`, and `authoritative: true`.

- [ ] **Step 8: Commit validation notes if any docs changed**

If validation adds no files, do not create an empty commit. If validation notes are added to docs, run:

```powershell
git add docs/CURRENT_ARCHITECTURE.md
git commit -m "docs: record capability discovery validation notes"
```

Expected: commit succeeds only if there are staged documentation changes.

## Phase 1 Review Checklist

Before asking for review, confirm:

- `GET /capabilities` exists only on RookNative.
- Native discovery still includes `capabilities.ghProvider` and `capabilities.ghRoutes`.
- Native discovery adds only additive fields.
- Native discovery marks `capabilities.domainSummary` as `bootstrap_snapshot`
  and non-authoritative, with `capabilities.liveEndpoint: "/capabilities"`.
- MCP resolves live readiness from `GET /capabilities` and uses
  `domainSummary` only as explicit stale/bootstrap fallback.
- Capability state is split by domain.
- `bim.rhino_inside_revit` is separate from GH.
- `chat.ui`, `vision.media`, `viewport.capture`, and `block.definition_mutation` are not collapsed into `gh.bridge`.
- `licensing.entitlement` is discoverable as reserved/future.
- No route ownership changed.
- No companion loading policy changed.
- No installer path, registry, or module manifest changed.
- No Revit API references were added under `src/Rook`.
- No `.vcxproj` or `.vcxproj.filters` files changed, unless the only project
  edit is the documented `RookServer.cpp` `/bigobj` exception.
- Existing startup/GH/BIM/chat/vision route behavior remains compatible.

## Final Verification Commands

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CapabilityDiscoverySourceTests|FullyQualifiedName~CompanionRuntimeStatusTests|FullyQualifiedName~ManagedCapabilityDomainStatusTests"
python -m pytest mcp_server/tests/test_bridge.py -k "capability_domain or rhino_inside_native_record" -q
cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
git diff --check origin/main...HEAD
```

Expected:

- Focused managed/source tests pass.
- Focused MCP tests pass.
- Native build passes with MSVC 14.44 and Rhino/MFC toolchain installed.
- `git diff --check origin/main...HEAD` exits 0.

Live validation remains required before marking the implementation PR ready:

- Standalone Rhino `/capabilities` smoke.
- Recent-file `_Open` startup gate.
- Existing GH/BIM/chat/vision route behavior smoke where touched surfaces are present.

## Self-Review

Spec coverage:

- Phase 1 capability schema: Tasks 1 and 3.
- Native public capability surface: Task 3.
- Discovery summary with backward compatibility: Tasks 1, 3, and 6.
- Domain inventory: Tasks 1 and 3.
- Evidence/state source requirement: Tasks 1, 3, 4, and 5.
- Managed readiness separated from native readiness: Tasks 3 and 4.
- BIM first-class boundary: Task 5.
- MCP/client discoverability: Task 6.
- No installer/module manifest work: Task 1 guard and Phase 1 boundaries.
- No behavior/loading/path changes: Phase 1 boundaries, Task 1 guard, and final checklist.

Placeholder scan:

- This plan contains no placeholder markers or unspecified implementation steps.
- Every code task names exact files and includes concrete code or command text.
- MCP parser support is included as a real Phase 1 slice, not left as optional work.

Type consistency:

- Native JSON uses `schemaVersion`, `domainId`, `stateSource`, `reasonCode`, `domainSummary`, and `capabilityDomains`.
- Managed records use PascalCase property names and serialize to camelCase through the existing `JsonSerializerOptions`.
- MCP helper preserves `domainSummary` but resolves live readiness through
  `GET /capabilities` when available.
