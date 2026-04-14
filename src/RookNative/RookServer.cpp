// RookServer.cpp

#include "stdafx.h"
#include "RookServer.h"
#include "Handlers/DocumentHandler.h"
#include "Handlers/LayersHandler.h"
#include "Handlers/ObjectsHandler.h"
#include "Handlers/GeometryHandler.h"
#include "Handlers/CommandHandler.h"
#include "Handlers/CreateHandler.h"
#include "Handlers/GeometryOpsHandler.h"
#include "Handlers/LayerOpsHandler.h"
#include "Handlers/SelectionHandler.h"
#include "Handlers/ViewportHandler.h"
#include "Handlers/DisplayModeHandler.h"
#include "Handlers/MeasureHandler.h"
#include "Handlers/GroupsHandler.h"
#include "Handlers/DocumentOpsHandler.h"
#include "Handlers/MaterialsHandler.h"
#include "Handlers/LinetypesHandler.h"
#include "Handlers/ImportExportHandler.h"
#include "Handlers/BooleanHandler.h"
#include "Handlers/FilletChamferHandler.h"
#include "Handlers/AnalysisHandler.h"
#include "Handlers/CurvesHandler.h"
#include "Handlers/IntersectionHandler.h"
#include "Handlers/SplitTrimHandler.h"
#include "Handlers/OffsetBrepHandler.h"
#include "Handlers/MeshHandler.h"
#include "Handlers/SubDHandler.h"
#include "Handlers/BlocksHandler.h"
#include "Handlers/TextureMappingHandler.h"
#include "Handlers/GameExportHandler.h"
#include "Handlers/SceneGraphHandler.h"
#include "Handlers/CommandInteractiveHandler.h"
#include "Handlers/PromptHandler.h"
#include "Handlers/GumballHandler.h"
#include "Handlers/GumballContextHandler.h"
#include "Handlers/SessionHandler.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Interactive/SessionRecorder.h"  // C10: McpRequestGuard
#include "RookNativePlugin.h"             // IsRhinoInside() for discovery file

#include <filesystem>
#include <fstream>
#include <chrono>
#include <iomanip>
#include <set>
#include <sstream>

namespace fs = std::filesystem;

namespace
{
    constexpr const char* kNativeBindHost = "127.0.0.1";

    bool EndsWith(const std::string& value, const std::string& suffix)
    {
        return value.size() >= suffix.size()
            && value.compare(value.size() - suffix.size(), suffix.size(), suffix) == 0;
    }

    bool IsPidAlive(DWORD pid)
    {
        HANDLE process = ::OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
        if (process == nullptr)
        {
            return false;
        }

        DWORD exitCode = 0;
        const BOOL ok = ::GetExitCodeProcess(process, &exitCode);
        ::CloseHandle(process);
        return ok && exitCode == STILL_ACTIVE;
    }

    bool TryParseDiscoveryPid(const fs::path& filePath, DWORD& pid)
    {
        const std::string fileName = filePath.filename().string();

        if (fileName.rfind("instance-", 0) == 0 && fileName.size() > 22)
        {
            const size_t suffix = std::string("-native.json").size();
            if (fileName.size() > suffix && EndsWith(fileName, "-native.json"))
            {
                const std::string pidText = fileName.substr(9, fileName.size() - 9 - suffix);
                try
                {
                    pid = static_cast<DWORD>(std::stoul(pidText));
                    return true;
                }
                catch (...)
                {
                    return false;
                }
            }
        }

        if (fileName.rfind("native-", 0) == 0 && EndsWith(fileName, ".json"))
        {
            const std::string pidText = fileName.substr(7, fileName.size() - 12);
            try
            {
                pid = static_cast<DWORD>(std::stoul(pidText));
                return true;
            }
            catch (...)
            {
                return false;
            }
        }

        return false;
    }
}

// --- Singleton ---

CRookServer& CRookServer::Instance()
{
    static CRookServer instance;
    return instance;
}

CRookServer::CRookServer() = default;

CRookServer::~CRookServer()
{
    Stop();
}

// --- Response Helpers ---

void CRookServer::SendSuccess(httplib::Response& res, const nlohmann::json& data)
{
    nlohmann::json envelope;
    envelope["success"] = true;
    envelope["data"] = data;

    res.status = 200;
    res.set_content(envelope.dump(), "application/json");
}

void CRookServer::SendError(httplib::Response& res, const std::string& message)
{
    nlohmann::json envelope;
    envelope["success"] = false;
    envelope["data"] = message;

    res.status = 400;
    res.set_content(envelope.dump(), "application/json");
}

void CRookServer::SendErrorData(httplib::Response& res, const nlohmann::json& data)
{
    nlohmann::json envelope;
    envelope["success"] = false;
    envelope["data"] = data;

    res.status = 400;
    res.set_content(envelope.dump(), "application/json");
}

// --- Route Handlers ---

void CRookServer::HandlePing(const httplib::Request& /*req*/, httplib::Response& res)
{
    SendSuccess(res, "pong");
}

void CRookServer::HandleGrasshopperStatus(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperStatus(req, res);
}

void CRookServer::HandleGrasshopperDocument(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperDocument(req, res);
}

void CRookServer::HandleGrasshopperQuery(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperQuery(req, res);
}

void CRookServer::HandleGrasshopperSelection(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperSelection(req, res);
}

void CRookServer::HandleGrasshopperCategories(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperCategories(req, res);
}

void CRookServer::HandleGrasshopperLibrary(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperLibrary(req, res);
}

void CRookServer::HandleGrasshopperGetValue(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperGetValue(req, res);
}

void CRookServer::HandleGrasshopperSetValue(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperSetValue(req, res);
}

void CRookServer::HandleGrasshopperSetScript(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperSetScript(req, res);
}

void CRookServer::HandleGrasshopperScriptParams(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperScriptParams(req, res);
}

void CRookServer::HandleGrasshopperConnections(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperConnections(req, res);
}

void CRookServer::HandleGrasshopperDelete(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperDelete(req, res);
}

void CRookServer::HandleGrasshopperPreview(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperPreview(req, res);
}

void CRookServer::HandleGrasshopperClear(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperClear(req, res);
}

void CRookServer::HandleGrasshopperOpenDocument(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperOpenDocument(req, res);
}

void CRookServer::HandleGrasshopperNewDocument(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperNewDocument(req, res);
}

void CRookServer::HandleGrasshopperMove(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperMove(req, res);
}

void CRookServer::HandleGrasshopperGroup(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperGroup(req, res);
}

void CRookServer::HandleGrasshopperGroups(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperGroups(req, res);
}

void CRookServer::HandleGrasshopperGroupResize(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperGroupResize(req, res);
}

void CRookServer::HandleGrasshopperCluster(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperCluster(req, res);
}

void CRookServer::HandleGrasshopperExploreSelection(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperExploreSelection(req, res);
}

void CRookServer::HandleGrasshopperExploreCluster(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperExploreCluster(req, res);
}

void CRookServer::HandleGrasshopperBatchComponentInfo(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperBatchComponentInfo(req, res);
}

void CRookServer::HandleGrasshopperCreateComponent(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperCreateComponent(req, res);
}

void CRookServer::HandleGrasshopperCreateSlider(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperCreateSlider(req, res);
}

void CRookServer::HandleGrasshopperCreatePanel(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperCreatePanel(req, res);
}

void CRookServer::HandleGrasshopperComponent(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperComponent(req, res);
}

void CRookServer::HandleGrasshopperInspectOutput(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperInspectOutput(req, res);
}

void CRookServer::HandleGrasshopperErrors(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperErrors(req, res);
}

void CRookServer::HandleGrasshopperConnect(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperConnect(req, res);
}

void CRookServer::HandleGrasshopperDisconnect(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperDisconnect(req, res);
}

void CRookServer::HandleGrasshopperSetReference(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperSetReference(req, res);
}

void CRookServer::HandleGrasshopperGetReference(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperGetReference(req, res);
}

void CRookServer::HandleGrasshopperClearReference(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperClearReference(req, res);
}

void CRookServer::HandleGrasshopperSolve(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperSolve(req, res);
}

void CRookServer::HandleGrasshopperBakeOutput(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperBakeOutput(req, res);
}

void CRookServer::HandleGrasshopperSnapshot(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperSnapshot(req, res);
}

void CRookServer::HandleGrasshopperEdit(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperEdit(req, res);
}

void CRookServer::HandleGrasshopperUndo(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperUndo(req, res);
}

void CRookServer::HandleGrasshopperCanvasFocus(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperCanvasFocus(req, res);
}

void CRookServer::HandleGrasshopperCanvasZoom(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperCanvasZoom(req, res);
}

void CRookServer::HandleGrasshopperCanvasImage(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGrasshopperCanvasImage(req, res);
}

void CRookServer::HandleManagedBlockSetLayers(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleManagedBlockSetLayers(req, res);
}

void CRookServer::HandleManagedBlockSetMaterials(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleManagedBlockSetMaterials(req, res);
}

void CRookServer::HandleBlockSetInstancePropertiesRoute(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockSetInstanceProperties(req, res);
}

void CRookServer::HandleBlockSetInstanceVisibilityRoute(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockSetInstanceVisibility(req, res);
}

void CRookServer::HandleBlockTransformInstanceRoute(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockTransformInstance(req, res);
}

void CRookServer::HandleBlockArrayInstancesRoute(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockArrayInstances(req, res);
}

void CRookServer::HandleManagedBlockSetObjectColors(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleManagedBlockSetObjectColors(req, res);
}

void CRookServer::HandleManagedBlockSetObjectNames(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleManagedBlockSetObjectNames(req, res);
}

void CRookServer::HandleManagedBlockSetObjectUserStrings(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleManagedBlockSetObjectUserStrings(req, res);
}

void CRookServer::HandleManagedBlockReplaceObjectGeometry(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleManagedBlockReplaceObjectGeometry(req, res);
}

void CRookServer::HandleManagedBlockTransformObject(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleManagedBlockTransformObject(req, res);
}

void CRookServer::HandleBlockFindInstancesRoute(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockFindInstances(req, res);
}

void CRookServer::HandleBlockUserStringsRoute(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockUserStrings(req, res);
}

void CRookServer::HandleBlockObjectsDetailedRoute(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockObjectsDetailed(req, res);
}

void CRookServer::HandleMake2d(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMake2d(req, res);
}

// --- Route Registration ---

// GH route auto-discovery: routes are recorded here during RegisterRoutes()
// so GetNativeGrasshopperRoutes() never drifts out of sync.
namespace {
    std::set<std::string> s_ghBaseRoutes;     // always advertised
    std::set<std::string> s_ghCgpRoutes;      // advertised when CGP callbacks registered
    std::set<std::string> s_ghNavRoutes;       // advertised when Nav callbacks registered
}

void CRookServer::RegisterRoutes()
{
    // Clear route sets in case of port retry (RegisterRoutes may be called more than once)
    s_ghBaseRoutes.clear();
    s_ghCgpRoutes.clear();
    s_ghNavRoutes.clear();

    // No CORS headers. Native server consumers (Python httpx, C# HttpClient,
    // agents) are not browsers and ignore CORS entirely. Omitting these headers
    // causes browsers to block cross-origin responses, and JSON POSTs fail
    // preflight so the actual request is never sent — breaking the
    // browser-to-RCE chain. Chat server CORS is separate (Phase 4).

    // Phase 1
    m_server->Get("/ping", [this](const httplib::Request& req, httplib::Response& res) {
        HandlePing(req, res);
    });
    m_server->Post("/make2d", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMake2d(req, res);
    });

    // --- GH route helpers: register with httplib AND record for discovery ---
    auto ghGet = [&](const char* path, auto handler) {
        m_server->Get(path, handler);
        s_ghBaseRoutes.insert(path);
    };
    auto ghPost = [&](const char* path, auto handler) {
        m_server->Post(path, handler);
        s_ghBaseRoutes.insert(path);
    };
    auto cgpPost = [&](const char* path, auto handler) {
        m_server->Post(path, handler);
        s_ghCgpRoutes.insert(path);
    };
    auto navPost = [&](const char* path, auto handler) {
        m_server->Post(path, handler);
        s_ghNavRoutes.insert(path);
    };
    auto navGet = [&](const char* path, auto handler) {
        m_server->Get(path, handler);
        s_ghNavRoutes.insert(path);
    };

    // Grasshopper: base routes (always advertised)
    ghGet("/gh/status", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperStatus(req, res);
    });
    ghGet("/gh/document", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperDocument(req, res);
    });
    ghGet("/gh/query", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperQuery(req, res);
    });
    ghGet("/gh/selection", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperSelection(req, res);
    });
    ghGet("/gh/categories", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperCategories(req, res);
    });
    ghGet("/gh/library", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperLibrary(req, res);
    });
    ghGet("/gh/value", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperGetValue(req, res);
    });
    ghPost("/gh/value", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperSetValue(req, res);
    });
    ghPost("/gh/script", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperSetScript(req, res);
    });
    ghPost("/gh/script-params", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperScriptParams(req, res);
    });
    ghGet("/gh/connections", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperConnections(req, res);
    });
    ghPost("/gh/delete", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperDelete(req, res);
    });
    ghPost("/gh/preview", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperPreview(req, res);
    });
    ghPost("/gh/clear", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperClear(req, res);
    });
    ghPost("/gh/document/open", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperOpenDocument(req, res);
    });
    ghPost("/gh/document/new", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperNewDocument(req, res);
    });
    ghPost("/gh/move", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperMove(req, res);
    });
    ghPost("/gh/group", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperGroup(req, res);
    });
    ghGet("/gh/groups", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperGroups(req, res);
    });
    ghPost("/gh/group-resize", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperGroupResize(req, res);
    });
    ghPost("/gh/cluster", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperCluster(req, res);
    });
    ghPost("/gh/explore-selection", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperExploreSelection(req, res);
    });
    ghPost("/gh/explore-cluster", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperExploreCluster(req, res);
    });
    ghPost("/gh/batch-component-info", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperBatchComponentInfo(req, res);
    });
    ghPost("/gh/create-component", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperCreateComponent(req, res);
    });
    ghPost("/gh/create-slider", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperCreateSlider(req, res);
    });
    ghPost("/gh/create-panel", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperCreatePanel(req, res);
    });
    ghGet("/gh/component", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperComponent(req, res);
    });
    ghGet("/gh/inspect-output", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperInspectOutput(req, res);
    });
    ghGet("/gh/errors", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperErrors(req, res);
    });
    ghPost("/gh/connect", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperConnect(req, res);
    });
    ghPost("/gh/disconnect", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperDisconnect(req, res);
    });
    ghPost("/gh/set-reference", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperSetReference(req, res);
    });
    ghGet("/gh/get-reference", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperGetReference(req, res);
    });
    ghPost("/gh/clear-reference", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperClearReference(req, res);
    });
    ghPost("/gh/solve", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperSolve(req, res);
    });
    ghPost("/gh/bake", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperBakeOutput(req, res);
    });

    // Canvas Graph Protocol — conditionally advertised when C# callbacks registered
    cgpPost("/gh/snapshot", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperSnapshot(req, res);
    });
    cgpPost("/gh/edit", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperEdit(req, res);
    });
    cgpPost("/gh/undo", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperUndo(req, res);
    });
    navPost("/gh/canvas/focus", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperCanvasFocus(req, res);
    });
    navPost("/gh/canvas/zoom", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperCanvasZoom(req, res);
    });
    navGet("/gh/canvas/image", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGrasshopperCanvasImage(req, res);
    });

    // Phase 2: Read-only handlers
    m_server->Get("/document", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDocument(req, res);
    });
    m_server->Get("/layers", [this](const httplib::Request& req, httplib::Response& res) {
        HandleLayers(req, res);
    });
    m_server->Get("/objects", [this](const httplib::Request& req, httplib::Response& res) {
        HandleObjects(req, res);
    });
    m_server->Get("/objects/with-history", [this](const httplib::Request& req, httplib::Response& res) {
        HandleObjectsWithHistory(req, res);
    });
    m_server->Get(R"(/object/([0-9A-Fa-f-]+)/history)", [this](const httplib::Request& req, httplib::Response& res) {
        HandleObjectHistory(req, res);
    });
    m_server->Get("/geometry", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGeometry(req, res);
    });

    // Phase 4A: Write handlers
    m_server->Post("/command", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCommand(req, res);
    });
    m_server->Post("/execute", [this](const httplib::Request& req, httplib::Response& res) {
        HandleExecute(req, res);
    });
    m_server->Post("/create", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCreate(req, res);
    });
    m_server->Post("/delete", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDelete(req, res);
    });
    m_server->Post("/transform", [this](const httplib::Request& req, httplib::Response& res) {
        HandleTransform(req, res);
    });
    m_server->Post("/copy", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCopy(req, res);
    });
    m_server->Post("/undo", [this](const httplib::Request& req, httplib::Response& res) {
        HandleUndo(req, res);
    });
    m_server->Post("/redo", [this](const httplib::Request& req, httplib::Response& res) {
        HandleRedo(req, res);
    });

    // Phase 4B: Layer management
    m_server->Post("/layers", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCreateLayer(req, res);
    });
    m_server->Post("/layers/batch", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCreateLayersBatch(req, res);
    });
    m_server->Delete("/layers", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDeleteLayer(req, res);
    });
    m_server->Post("/layers/visibility", [this](const httplib::Request& req, httplib::Response& res) {
        HandleLayerVisibility(req, res);
    });
    m_server->Post("/layers/lock", [this](const httplib::Request& req, httplib::Response& res) {
        HandleLayerLock(req, res);
    });
    m_server->Post("/layers/current", [this](const httplib::Request& req, httplib::Response& res) {
        HandleLayerCurrent(req, res);
    });
    m_server->Post("/layers/properties", [this](const httplib::Request& req, httplib::Response& res) {
        HandleLayerSetProperties(req, res);
    });
    m_server->Post("/layers/rename", [this](const httplib::Request& req, httplib::Response& res) {
        HandleLayerRename(req, res);
    });
    m_server->Post("/layers/move-objects", [this](const httplib::Request& req, httplib::Response& res) {
        HandleLayerMoveObjects(req, res);
    });
    m_server->Post("/layers/merge", [this](const httplib::Request& req, httplib::Response& res) {
        HandleLayerMerge(req, res);
    });
    m_server->Get("/layers/dependencies", [this](const httplib::Request& req, httplib::Response& res) {
        HandleLayerDependencies(req, res);
    });

    // Phase 4B: Selection
    m_server->Get("/selection", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGetSelection(req, res);
    });
    m_server->Post("/select", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSelect(req, res);
    });

    // Phase 4B: Viewport
    m_server->Post("/viewport", [this](const httplib::Request& req, httplib::Response& res) {
        HandleViewport(req, res);
    });
    m_server->Get("/display-modes", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGetDisplayModes(req, res);
    });
    m_server->Post("/display-mode", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSetDisplayMode(req, res);
    });

    // Phase 4B: Measurements (dual GET/POST registration)
    m_server->Get("/measure/distance", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureDistance(req, res);
    });
    m_server->Post("/measure/distance", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureDistance(req, res);
    });
    m_server->Get("/measure/area", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureArea(req, res);
    });
    m_server->Post("/measure/area", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureArea(req, res);
    });
    m_server->Get("/measure/volume", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureVolume(req, res);
    });
    m_server->Post("/measure/volume", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureVolume(req, res);
    });
    m_server->Get("/measure/length", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureLength(req, res);
    });
    m_server->Post("/measure/length", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureLength(req, res);
    });
    m_server->Get("/measure/bbox", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureBbox(req, res);
    });
    m_server->Post("/measure/bbox", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureBbox(req, res);
    });
    m_server->Get("/measure/centroid", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureCentroid(req, res);
    });
    m_server->Post("/measure/centroid", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeasureCentroid(req, res);
    });

    // Phase 4C: Groups
    m_server->Get("/groups", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGetGroups(req, res);
    });
    m_server->Post("/group", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGroup(req, res);
    });
    m_server->Post("/ungroup", [this](const httplib::Request& req, httplib::Response& res) {
        HandleUngroup(req, res);
    });
    m_server->Get("/group/members", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGroupMembers(req, res);
    });

    // Phase 4C: Document operations
    m_server->Post("/document/open", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDocumentOpen(req, res);
    });
    m_server->Post("/document/save", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDocumentSave(req, res);
    });
    m_server->Post("/document/new", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDocumentNew(req, res);
    });
    m_server->Post("/document/units", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDocumentUnits(req, res);
    });
    m_server->Get("/views", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGetViews(req, res);
    });
    m_server->Post("/views/save", [this](const httplib::Request& req, httplib::Response& res) {
        HandleViewsSave(req, res);
    });
    m_server->Post("/views/restore", [this](const httplib::Request& req, httplib::Response& res) {
        HandleViewsRestore(req, res);
    });

    // Phase 4C: Materials
    m_server->Get("/materials", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGetMaterials(req, res);
    });
    m_server->Post("/materials", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCreateMaterial(req, res);
    });
    m_server->Delete("/materials", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDeleteMaterial(req, res);
    });
    m_server->Post("/materials/assign", [this](const httplib::Request& req, httplib::Response& res) {
        HandleAssignMaterial(req, res);
    });
    m_server->Post("/materials/purge", [this](const httplib::Request& req, httplib::Response& res) {
        HandlePurgeMaterials(req, res);
    });

    // Linetypes
    m_server->Get("/linetypes", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGetLinetypes(req, res);
    });
    m_server->Post("/linetypes/purge", [this](const httplib::Request& req, httplib::Response& res) {
        HandlePurgeLinetypes(req, res);
    });

    // Phase 4C: Import/Export
    m_server->Post("/import", [this](const httplib::Request& req, httplib::Response& res) {
        HandleImport(req, res);
    });
    m_server->Post("/export", [this](const httplib::Request& req, httplib::Response& res) {
        HandleExport(req, res);
    });

    // Phase 4C: Boolean operations
    m_server->Post("/boolean", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBoolean(req, res);
    });

    // Phase 4C: Fillet, Chamfer, Offset
    m_server->Post("/fillet", [this](const httplib::Request& req, httplib::Response& res) {
        HandleFillet(req, res);
    });
    m_server->Post("/chamfer", [this](const httplib::Request& req, httplib::Response& res) {
        HandleChamfer(req, res);
    });
    m_server->Post("/offset", [this](const httplib::Request& req, httplib::Response& res) {
        HandleOffset(req, res);
    });

    // Phase 4D: Analysis
    m_server->Post("/analysis/curvature-curve", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurvatureCurve(req, res);
    });
    m_server->Post("/analysis/curvature-surface", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurvatureSurface(req, res);
    });
    m_server->Post("/analysis/draft-angle", [this](const httplib::Request& req, httplib::Response& res) {
        HandleDraftAngle(req, res);
    });
    m_server->Post("/analysis/closest-point", [this](const httplib::Request& req, httplib::Response& res) {
        HandleClosestPoint(req, res);
    });
    m_server->Post("/analysis/curve-point-at", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurvePointAt(req, res);
    });
    m_server->Post("/analysis/curve-tangent", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveTangent(req, res);
    });
    m_server->Post("/analysis/curve-frame", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveFrame(req, res);
    });
    m_server->Post("/analysis/surface-normal", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSurfaceNormal(req, res);
    });
    m_server->Post("/analysis/brep-edges", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBrepEdges(req, res);
    });
    m_server->Post("/analysis/brep-faces", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBrepFaces(req, res);
    });
    m_server->Post("/analysis/brep-vertices", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBrepVertices(req, res);
    });
    m_server->Post("/analysis/is-closed", [this](const httplib::Request& req, httplib::Response& res) {
        HandleIsClosed(req, res);
    });
    m_server->Post("/analysis/is-valid", [this](const httplib::Request& req, httplib::Response& res) {
        HandleIsValid(req, res);
    });

    // Phase 4D: Curves
    m_server->Post("/curve/join", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveJoin(req, res);
    });
    m_server->Post("/curve/explode", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveExplode(req, res);
    });
    m_server->Post("/curve/divide", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveDivide(req, res);
    });
    m_server->Post("/curve/extend", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveExtend(req, res);
    });
    m_server->Post("/curve/trim", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveTrim(req, res);
    });
    m_server->Post("/curve/split", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveSplit(req, res);
    });
    m_server->Post("/curve/rebuild", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveRebuild(req, res);
    });
    m_server->Post("/curve/fillet", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveFillet(req, res);
    });
    m_server->Post("/curve/project", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveProject(req, res);
    });
    m_server->Post("/curve/pull", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurvePull(req, res);
    });
    m_server->Post("/curve/offset", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveOffset(req, res);
    });
    m_server->Post("/curve/offset-on-surface", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCurveOffsetOnSurface(req, res);
    });

    // Phase 4E: Intersections
    m_server->Post("/intersect/curves", [this](const httplib::Request& req, httplib::Response& res) {
        HandleIntersectCurves(req, res);
    });
    m_server->Post("/intersect/curve-surface", [this](const httplib::Request& req, httplib::Response& res) {
        HandleIntersectCurveSurface(req, res);
    });
    m_server->Post("/intersect/curve-brep", [this](const httplib::Request& req, httplib::Response& res) {
        HandleIntersectCurveBrep(req, res);
    });
    m_server->Post("/intersect/breps", [this](const httplib::Request& req, httplib::Response& res) {
        HandleIntersectBreps(req, res);
    });
    m_server->Post("/intersect/plane", [this](const httplib::Request& req, httplib::Response& res) {
        HandleIntersectPlane(req, res);
    });
    m_server->Post("/road/intersection/candidates", [this](const httplib::Request& req, httplib::Response& res) {
        HandleRoadIntersectionCandidates(req, res);
    });
    m_server->Post("/road/intersection/analyze", [this](const httplib::Request& req, httplib::Response& res) {
        HandleRoadIntersectionAnalyze(req, res);
    });
    m_server->Post("/road/intersection/commit", [this](const httplib::Request& req, httplib::Response& res) {
        HandleRoadIntersectionCommit(req, res);
    });
    m_server->Post("/road/intersection/resolve", [this](const httplib::Request& req, httplib::Response& res) {
        HandleRoadIntersectionResolve(req, res);
    });

    // Phase 4E: Split/Trim
    m_server->Post("/split/brep", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSplitBrep(req, res);
    });
    m_server->Post("/trim/brep", [this](const httplib::Request& req, httplib::Response& res) {
        HandleTrimBrep(req, res);
    });
    m_server->Post("/split/face", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSplitFace(req, res);
    });
    m_server->Post("/split/disjoint-breps", [](const httplib::Request& req, httplib::Response& res) {
        Rook::Handlers::HandleSplitDisjointBreps(req, res);
    });

    // Phase 4E: Offset Brep
    m_server->Post("/offset/brep", [this](const httplib::Request& req, httplib::Response& res) {
        HandleOffsetBrep(req, res);
    });

    // Phase 4E: Mesh operations
    m_server->Post("/mesh/from-brep", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshFromBrep(req, res);
    });
    m_server->Post("/mesh/box", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshBox(req, res);
    });
    m_server->Post("/mesh/sphere", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshSphere(req, res);
    });
    m_server->Post("/mesh/cylinder", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshCylinder(req, res);
    });
    m_server->Post("/mesh/cone", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshCone(req, res);
    });
    m_server->Post("/mesh/boolean", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshBoolean(req, res);
    });
    m_server->Post("/mesh/reduce", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshReduce(req, res);
    });
    m_server->Post("/mesh/quad-remesh", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshQuadRemesh(req, res);
    });
    m_server->Post("/mesh/repair", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshRepair(req, res);
    });
    m_server->Post("/mesh/smooth", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshSmooth(req, res);
    });
    m_server->Post("/mesh/weld", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshWeld(req, res);
    });
    m_server->Post("/mesh/unweld", [this](const httplib::Request& req, httplib::Response& res) {
        HandleMeshUnweld(req, res);
    });

    // Phase 4E: SubD operations
    m_server->Post("/subd/box", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSubDBox(req, res);
    });
    m_server->Post("/subd/sphere", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSubDSphere(req, res);
    });
    m_server->Post("/subd/cylinder", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSubDCylinder(req, res);
    });
    m_server->Post("/subd/from-mesh", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSubDFromMesh(req, res);
    });
    m_server->Post("/subd/from-surface", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSubDFromSurface(req, res);
    });
    m_server->Post("/subd/subdivide", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSubDSubdivide(req, res);
    });
    m_server->Post("/subd/crease", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSubDCrease(req, res);
    });
    m_server->Post("/subd/to-brep", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSubDToBrep(req, res);
    });
    m_server->Post("/subd/to-mesh", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSubDToMesh(req, res);
    });

    // Phase 4F: Blocks
    m_server->Get("/blocks", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGetBlocks(req, res);
    });
    m_server->Post("/block/create", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockCreate(req, res);
    });
    m_server->Post("/block/insert", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockInsert(req, res);
    });
    m_server->Post("/block/explode", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockExplode(req, res);
    });
    m_server->Delete("/block", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockDelete(req, res);
    });
    m_server->Post("/block/rename", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockRename(req, res);
    });
    m_server->Post("/block/description", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockDescription(req, res);
    });
    m_server->Get("/block/info", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockInfo(req, res);
    });
    m_server->Post("/block/info", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockInfo(req, res);
    });
    m_server->Post("/block/add-objects", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockAddObjects(req, res);
    });
    m_server->Post("/block/remove-objects", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockRemoveObjects(req, res);
    });
    m_server->Post("/block/replace-geometry", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockReplaceGeometry(req, res);
    });
    m_server->Get("/block/instances", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockInstances(req, res);
    });
    m_server->Post("/block/instances", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockInstances(req, res);
    });
    m_server->Post("/block/replace-instance", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockReplaceInstance(req, res);
    });
    m_server->Post("/block/reset-scale", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockResetScale(req, res);
    });
    m_server->Post("/block/link", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockLink(req, res);
    });
    m_server->Post("/block/refresh", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockRefresh(req, res);
    });
    m_server->Post("/block/unlink", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockUnlink(req, res);
    });
    m_server->Post("/block/purge", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockPurge(req, res);
    });
    m_server->Post("/block/duplicate", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockDuplicate(req, res);
    });
    m_server->Post("/block/rebase", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockRebase(req, res);
    });
    m_server->Post("/block/rebase-recursive", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockRebaseRecursive(req, res);
    });
    m_server->Get("/block/nested", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockNested(req, res);
    });
    m_server->Post("/block/nested", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockNested(req, res);
    });
    // Intentionally companion-backed: native instance-definition mutation for this
    // five-route subfamily is paused after live Rhino crash reproduction.
    m_server->Post("/block/set-layers", [this](const httplib::Request& req, httplib::Response& res) {
        HandleManagedBlockSetLayers(req, res);
    });
    m_server->Post("/block/set-materials", [this](const httplib::Request& req, httplib::Response& res) {
        HandleManagedBlockSetMaterials(req, res);
    });
    m_server->Post("/block/set-instance-properties", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockSetInstancePropertiesRoute(req, res);
    });
    m_server->Post("/block/set-instance-visibility", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockSetInstanceVisibilityRoute(req, res);
    });
    m_server->Post("/block/transform-instance", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockTransformInstanceRoute(req, res);
    });
    m_server->Post("/block/array-instances", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockArrayInstancesRoute(req, res);
    });
    m_server->Post("/block/set-object-colors", [this](const httplib::Request& req, httplib::Response& res) {
        HandleManagedBlockSetObjectColors(req, res);
    });
    m_server->Post("/block/set-object-names", [this](const httplib::Request& req, httplib::Response& res) {
        HandleManagedBlockSetObjectNames(req, res);
    });
    m_server->Post("/block/set-object-user-strings", [this](const httplib::Request& req, httplib::Response& res) {
        HandleManagedBlockSetObjectUserStrings(req, res);
    });
    // Companion-backed: per-object geometry mutations (same category as set-layers family)
    m_server->Post("/block/replace-object-geometry", [this](const httplib::Request& req, httplib::Response& res) {
        HandleManagedBlockReplaceObjectGeometry(req, res);
    });
    m_server->Post("/block/transform-object", [this](const httplib::Request& req, httplib::Response& res) {
        HandleManagedBlockTransformObject(req, res);
    });
    m_server->Post("/block/find-instances", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockFindInstancesRoute(req, res);
    });
    m_server->Get("/block/user-strings", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockUserStringsRoute(req, res);
    });
    m_server->Post("/block/user-strings", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockUserStringsRoute(req, res);
    });
    m_server->Get("/block/objects-detailed", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockObjectsDetailedRoute(req, res);
    });
    m_server->Post("/block/objects-detailed", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockObjectsDetailedRoute(req, res);
    });
    // Block deduplication
    m_server->Post("/block/compare", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockCompare(req, res);
    });
    m_server->Post("/block/merge", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockMerge(req, res);
    });
    m_server->Get("/block/layer-census", [this](const httplib::Request& req, httplib::Response& res) {
        HandleBlockLayerCensus(req, res);
    });

    // Phase 4F: Texture Mapping
    m_server->Post("/material/uv-box", [this](const httplib::Request& req, httplib::Response& res) {
        HandleUvBox(req, res);
    });
    m_server->Post("/material/uv-planar", [this](const httplib::Request& req, httplib::Response& res) {
        HandleUvPlanar(req, res);
    });
    m_server->Post("/material/uv-cylinder", [this](const httplib::Request& req, httplib::Response& res) {
        HandleUvCylinder(req, res);
    });
    m_server->Post("/material/uv-sphere", [this](const httplib::Request& req, httplib::Response& res) {
        HandleUvSphere(req, res);
    });

    // Phase 4F: Game Export
    m_server->Post("/game-export/tag", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGameExportTag(req, res);
    });
    m_server->Post("/game-export/tag-from-layers", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGameExportTagFromLayers(req, res);
    });
    m_server->Post("/game-export/validate", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGameExportValidate(req, res);
    });
    m_server->Post("/game-export/export", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGameExportExport(req, res);
    });
    m_server->Post("/game-export/prepare", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGameExportPrepare(req, res);
    });

    // Phase 3: Scene Graph
    m_server->Get("/scene/graph", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSceneGraph(req, res);
    });
    m_server->Get("/scene/graph/node", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSceneGraphNode(req, res);
    });
    m_server->Post("/scene/graph/node", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSceneGraphNode(req, res);
    });
    m_server->Post("/scene/graph/query", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSceneGraphQuery(req, res);
    });
    m_server->Get("/scene/graph/stats", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSceneGraphStats(req, res);
    });
    m_server->Post("/scene/graph/diff", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSceneGraphDiff(req, res);
    });
    m_server->Post("/scene/graph/reconcile", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSceneGraphReconcile(req, res);
    });
    m_server->Post("/scene/graph/classify", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSceneGraphClassify(req, res);
    });
    m_server->Post("/scene/graph/overlay", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSceneGraphOverlay(req, res);
    });

    // Phase 5: Command Interactive
    m_server->Get("/command/prompt", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCommandPrompt(req, res);
    });
    m_server->Post("/command/start", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCommandStart(req, res);
    });
    m_server->Post("/command/send", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCommandInput(req, res);
    });
    m_server->Post("/command/cancel", [this](const httplib::Request& req, httplib::Response& res) {
        HandleCommandCancel(req, res);
    });

    // Phase 5: User Prompts
    m_server->Post("/prompt/point", [this](const httplib::Request& req, httplib::Response& res) {
        HandlePromptPoint(req, res);
    });
    m_server->Post("/prompt/object", [this](const httplib::Request& req, httplib::Response& res) {
        HandlePromptObject(req, res);
    });
    m_server->Post("/prompt/objects", [this](const httplib::Request& req, httplib::Response& res) {
        HandlePromptObjects(req, res);
    });
    m_server->Post("/prompt/subobject", [this](const httplib::Request& req, httplib::Response& res) {
        HandlePromptSubObject(req, res);
    });
    m_server->Post("/prompt/distance", [this](const httplib::Request& req, httplib::Response& res) {
        HandlePromptDistance(req, res);
    });

    // Phase 5: AI Gumball
    m_server->Post("/gumball/activate", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballActivate(req, res);
    });
    m_server->Post("/gumball/deactivate", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballDeactivate(req, res);
    });
    m_server->Get("/gumball/status", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballStatus(req, res);
    });
    m_server->Get("/gumball/history", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballHistory(req, res);
    });

    // Phase 6A: AI Gumball v2 — Context, Alignment, Appearance
    m_server->Get("/gumball/context", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballContext(req, res);
    });
    m_server->Post("/gumball/align", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballAlign(req, res);
    });
    m_server->Post("/gumball/appearance", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballAppearance(req, res);
    });
    m_server->Post("/gumball/extrude", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballExtrude(req, res);
    });
    m_server->Post("/gumball/cut", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballCut(req, res);
    });
    m_server->Post("/gumball/settings", [this](const httplib::Request& req, httplib::Response& res) {
        HandleGumballSettings(req, res);
    });

    // Phase 5: Session Recording
    m_server->Get("/session", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSessionCurrent(req, res);
    });
    m_server->Get("/session/history", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSessionHistory(req, res);
    });
    m_server->Get("/session/list", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSessionList(req, res);
    });
    m_server->Post("/session/export", [this](const httplib::Request& req, httplib::Response& res) {
        HandleSessionExport(req, res);
    });

    // Catch-all for unknown routes
    m_server->set_error_handler([](const httplib::Request& req, httplib::Response& res) {
        if (res.status == 404)
        {
            nlohmann::json envelope;
            envelope["success"] = false;
            envelope["data"] = "Unknown endpoint: " + req.method + " " + req.path;
            res.set_content(envelope.dump(), "application/json");
        }
    });

    // Exception handler — maintains the JSON envelope contract on unhandled throws.
    // Without this, httplib returns a 500 with an empty body and a non-standard header.
    m_server->set_exception_handler(
        [](const httplib::Request& /*req*/, httplib::Response& res, std::exception_ptr ep) {
            std::string what = "Unknown internal error";
            try
            {
                if (ep) std::rethrow_exception(ep);
            }
            catch (const std::exception& e) { what = e.what(); }
            catch (...) {}

            nlohmann::json envelope;
            envelope["success"] = false;
            envelope["data"] = what;
            res.status = 500;
            res.set_content(envelope.dump(), "application/json");
        });
}

// --- Discovery File ---

namespace
{

nlohmann::json GetNativeGrasshopperRoutes()
{
    // Auto-derived from RegisterRoutes() — no hand-maintained array to drift.
    auto routes = nlohmann::json::array();
    for (const auto& r : s_ghBaseRoutes)
        routes.push_back(r);

    if (Rook::Handlers::HasCanvasGraphProtocol())
        for (const auto& r : s_ghCgpRoutes)
            routes.push_back(r);

    if (Rook::Handlers::HasCanvasGraphNavigation())
        for (const auto& r : s_ghNavRoutes)
            routes.push_back(r);

    return routes;
}

} // namespace

std::string CRookServer::GetDiscoveryFolder()
{
    // %TEMP%/rook/ — same location as C# plugin's discovery files
    return (fs::temp_directory_path() / "rook").string();
}

std::string CRookServer::GetDiscoveryFilePath()
{
    DWORD pid = ::GetCurrentProcessId();
    return GetDiscoveryFolder() + "\\instance-" + std::to_string(pid) + "-native.json";
}

void CRookServer::WriteDiscoveryFile()
{
    // NOTE: If Rhino crashes, this file will be orphaned on disk.
    // The Python MCP server (bridge.py) should check process liveness
    // before trusting a discovery file — same pattern as the C# plugin's
    // CleanupStaleDiscoveryFiles() which verifies PIDs are still alive.
    try
    {
        std::string folder = GetDiscoveryFolder();
        fs::create_directories(folder);

        // ISO 8601 timestamp
        auto now = std::chrono::system_clock::now();
        auto time = std::chrono::system_clock::to_time_t(now);
        std::ostringstream ts;
        struct tm tm_buf = {};
        if (localtime_s(&tm_buf, &time) == 0)
        {
            ts << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%S");
        }
        else
        {
            ts << time;
        }

        nlohmann::json info;
        info["host"] = kNativeBindHost;
        info["port"] = m_port;
        info["pluginType"] = "native";
        info["processId"] = ::GetCurrentProcessId();
        info["startTime"] = ts.str();
        info["pluginVersion"] = "1.5.1";
        info["rhinoInside"] = CRookNativePlugin::IsRhinoInside();
        const auto ghRoutes = GetNativeGrasshopperRoutes();
        const bool callbackBridgeReady = Rook::Handlers::HasGrasshopperBridgeRegistration();
        info["capabilities"] = {
            {"ghProvider", "callback"},
            {"ghRoutes", callbackBridgeReady ? ghRoutes : nlohmann::json::array()}
        };

        m_discovery_path = GetDiscoveryFilePath();

        // Atomic write: write to .tmp then rename to avoid torn reads
        // from Python bridge polling the same directory.
        std::string tmp_path = m_discovery_path + ".tmp";
        std::ofstream file(tmp_path);
        if (!file.is_open())
        {
            RhinoApp().Print(L"RookNative: warning — cannot open discovery file for writing: %S\n",
                tmp_path.c_str());
            return;
        }
        file << info.dump(2);
        file.close();
        const auto tmp_path_w = fs::path(tmp_path).wstring();
        const auto discovery_path_w = fs::path(m_discovery_path).wstring();
        if (!::MoveFileExW(
                tmp_path_w.c_str(),
                discovery_path_w.c_str(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
        {
            const DWORD error = ::GetLastError();
            std::ostringstream message;
            message << "MoveFileExW failed with error " << error;
            throw std::runtime_error(message.str());
        }
    }
    catch (const std::exception& ex)
    {
        RhinoApp().Print(L"RookNative: warning — failed to write discovery file: %S\n", ex.what());
    }
}

void CRookServer::RefreshDiscoveryFile()
{
    if (!m_running.load())
        return;

    WriteDiscoveryFile();
}

void CRookServer::RemoveDiscoveryFile()
{
    if (!m_discovery_path.empty())
    {
        try
        {
            fs::remove(m_discovery_path);
        }
        catch (...) {}
        m_discovery_path.clear();
    }
}

// --- Server Lifecycle ---

bool CRookServer::Start()
{
    if (m_running.load())
        return true;

    // Clean up ALL stale discovery files from crashed sessions.
    // Covers: instance-*-native.json, native-*.json (via TryParseDiscoveryPid),
    //         chat-service-*.json, instance-rc-*.json, companion-*.json (via JSON pid field).
    try
    {
        const fs::path discoveryFolder = GetDiscoveryFolder();
        if (fs::exists(discoveryFolder))
        {
            for (const auto& entry : fs::directory_iterator(discoveryFolder))
            {
                if (!entry.is_regular_file())
                    continue;

                const std::string fileName = entry.path().filename().string();

                // Try filename-based PID extraction first (fast, no JSON parse)
                DWORD pid = 0;
                if (TryParseDiscoveryPid(entry.path(), pid))
                {
                    if (!IsPidAlive(pid))
                        fs::remove(entry.path());
                    continue;
                }

                // For other known discovery file types, parse JSON and check PID
                const bool isChatService = fileName.rfind("chat-service-", 0) == 0 && EndsWith(fileName, ".json");
                const bool isRcInstance  = fileName.rfind("instance-rc-", 0) == 0 && EndsWith(fileName, ".json");
                const bool isCompanion   = fileName.rfind("companion-", 0) == 0 && EndsWith(fileName, ".json");

                if (!isChatService && !isRcInstance && !isCompanion)
                    continue;

                try
                {
                    std::ifstream f(entry.path());
                    if (!f.is_open())
                        continue;
                    auto data = nlohmann::json::parse(f, nullptr, false);
                    if (data.is_discarded())
                    {
                        fs::remove(entry.path());
                        continue;
                    }

                    DWORD filePid = 0;
                    if (data.contains("pid") && data["pid"].is_number_integer())
                        filePid = static_cast<DWORD>(data["pid"].get<int>());
                    else if (data.contains("processId") && data["processId"].is_number_integer())
                        filePid = static_cast<DWORD>(data["processId"].get<int>());

                    if (filePid > 0 && !IsPidAlive(filePid))
                        fs::remove(entry.path());
                }
                catch (...)
                {
                    // Malformed JSON — remove it
                    try { fs::remove(entry.path()); } catch (...) {}
                }
            }
        }
    }
    catch (...)
    {
    }

    // Let the OS assign a free port (port 0). No range scanning needed.
    m_server = std::make_unique<httplib::Server>();

    // Cap thread pool at 8. Default is hardware_concurrency-1, which on
    // a 32-core workstation creates 31 threads — wasteful since requests
    // serialize through the main thread dispatcher anyway.
    m_server->new_task_queue = [] { return new httplib::ThreadPool(8); };

    // Force exclusive port ownership on Windows.
    m_server->set_socket_options([](socket_t sock) {
#ifdef _WIN32
        int opt = 1;
        setsockopt(sock, SOL_SOCKET, SO_EXCLUSIVEADDRUSE,
                   reinterpret_cast<const char*>(&opt), sizeof(opt));
#else
        int opt = 1;
        setsockopt(sock, SOL_SOCKET, SO_REUSEADDR,
                   reinterpret_cast<const void*>(&opt), sizeof(opt));
#endif
    });

    // 30-second timeouts match the C# plugin's ManualResetEventSlim.Wait(30000).
    // Default 5s is too short once Phase 2+ handlers dispatch to the main thread.
    m_server->set_read_timeout(30);
    m_server->set_write_timeout(30);

    RegisterRoutes();

    const int bound_port = m_server->bind_to_any_port(kNativeBindHost);
    if (bound_port < 0)
    {
        RhinoApp().Print(L"RookNative: bind_to_any_port failed on %hs\n", kNativeBindHost);
        m_server.reset();
        return false;
    }

    m_port = bound_port;

    // Start listening in a background thread (listen_after_bind blocks)
    m_server_thread = std::thread([this]() {
        m_server->listen_after_bind();
    });

    // Wait for the server to be ready, then verify it actually started.
    // wait_until_ready can exit early if is_decommisioned was set.
    m_server->wait_until_ready();
    if (!m_server->is_running())
    {
        m_server_thread.join();
        m_server.reset();
        RhinoApp().Print(L"RookNative: server failed to start after binding port %d\n", bound_port);
        return false;
    }

    m_running.store(true);
    WriteDiscoveryFile();
    return true;
}

void CRookServer::Stop()
{
    if (!m_running.load())
        return;

    m_running.store(false);
    m_server->stop();

    if (m_server_thread.joinable())
    {
        m_server_thread.join();
    }

    RemoveDiscoveryFile();
    m_port = 0;
}

// --- Phase 2 Handler Delegates ---

void CRookServer::HandleDocument(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDocument(req, res);
}

void CRookServer::HandleLayers(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleLayers(req, res);
}

void CRookServer::HandleObjects(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleObjects(req, res);
}

void CRookServer::HandleObjectHistory(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleObjectHistory(req, res);
}

void CRookServer::HandleObjectsWithHistory(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleObjectsWithHistory(req, res);
}

void CRookServer::HandleGeometry(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGeometry(req, res);
}

// --- Phase 4 Handler Delegates ---

void CRookServer::HandleCommand(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleCommand(req, res);
}

void CRookServer::HandleExecute(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleExecute(req, res);
}

void CRookServer::HandleCreate(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleCreate(req, res);
}

void CRookServer::HandleDelete(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDelete(req, res);
}

void CRookServer::HandleTransform(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleTransform(req, res);
}

void CRookServer::HandleCopy(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCopy(req, res);
}

void CRookServer::HandleUndo(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleUndo(req, res);
}

void CRookServer::HandleRedo(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleRedo(req, res);
}

// --- Phase 4B Handler Delegates ---

void CRookServer::HandleCreateLayer(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCreateLayer(req, res);
}

void CRookServer::HandleCreateLayersBatch(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCreateLayersBatch(req, res);
}

void CRookServer::HandleDeleteLayer(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDeleteLayer(req, res);
}

void CRookServer::HandleLayerVisibility(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleLayerVisibility(req, res);
}

void CRookServer::HandleLayerLock(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleLayerLock(req, res);
}

void CRookServer::HandleLayerCurrent(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleLayerCurrent(req, res);
}

void CRookServer::HandleLayerSetProperties(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleLayerSetProperties(req, res);
}

void CRookServer::HandleLayerRename(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleLayerRename(req, res);
}

void CRookServer::HandleLayerMoveObjects(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleLayerMoveObjects(req, res);
}

void CRookServer::HandleLayerMerge(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleLayerMerge(req, res);
}

void CRookServer::HandleLayerDependencies(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleLayerDependencies(req, res);
}

void CRookServer::HandleGetSelection(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGetSelection(req, res);
}

void CRookServer::HandleSelect(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSelect(req, res);
}

void CRookServer::HandleViewport(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleViewport(req, res);
}

void CRookServer::HandleGetDisplayModes(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGetDisplayModes(req, res);
}

void CRookServer::HandleSetDisplayMode(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSetDisplayMode(req, res);
}

void CRookServer::HandleMeasureDistance(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeasureDistance(req, res);
}

void CRookServer::HandleMeasureArea(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeasureArea(req, res);
}

void CRookServer::HandleMeasureVolume(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeasureVolume(req, res);
}

void CRookServer::HandleMeasureLength(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeasureLength(req, res);
}

void CRookServer::HandleMeasureBbox(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeasureBbox(req, res);
}

void CRookServer::HandleMeasureCentroid(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeasureCentroid(req, res);
}

// --- Phase 4C Handler Delegates ---

void CRookServer::HandleGetGroups(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGetGroups(req, res);
}

void CRookServer::HandleGroup(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGroup(req, res);
}

void CRookServer::HandleUngroup(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleUngroup(req, res);
}

void CRookServer::HandleGroupMembers(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGroupMembers(req, res);
}

void CRookServer::HandleDocumentOpen(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleDocumentOpen(req, res);
}

void CRookServer::HandleDocumentSave(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleDocumentSave(req, res);
}

void CRookServer::HandleDocumentNew(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleDocumentNew(req, res);
}

void CRookServer::HandleDocumentUnits(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleDocumentUnits(req, res);
}

void CRookServer::HandleGetViews(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGetViews(req, res);
}

void CRookServer::HandleViewsSave(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleViewsSave(req, res);
}

void CRookServer::HandleViewsRestore(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleViewsRestore(req, res);
}

void CRookServer::HandleGetMaterials(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGetMaterials(req, res);
}

void CRookServer::HandleCreateMaterial(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCreateMaterial(req, res);
}

void CRookServer::HandleDeleteMaterial(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDeleteMaterial(req, res);
}

void CRookServer::HandleAssignMaterial(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleAssignMaterial(req, res);
}

void CRookServer::HandlePurgeMaterials(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandlePurgeMaterials(req, res);
}

void CRookServer::HandleGetLinetypes(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGetLinetypes(req, res);
}

void CRookServer::HandlePurgeLinetypes(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandlePurgeLinetypes(req, res);
}

void CRookServer::HandleImport(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleImport(req, res);
}

void CRookServer::HandleExport(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleExport(req, res);
}

void CRookServer::HandleBoolean(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleBoolean(req, res);
}

void CRookServer::HandleFillet(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleFillet(req, res);
}

void CRookServer::HandleChamfer(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleChamfer(req, res);
}

void CRookServer::HandleOffset(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleOffset(req, res);
}

// --- Phase 4D: Analysis delegates ---

void CRookServer::HandleCurvatureCurve(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurvatureCurve(req, res);
}

void CRookServer::HandleCurvatureSurface(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurvatureSurface(req, res);
}

void CRookServer::HandleDraftAngle(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleDraftAngle(req, res);
}

void CRookServer::HandleClosestPoint(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleClosestPoint(req, res);
}

void CRookServer::HandleCurvePointAt(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurvePointAt(req, res);
}

void CRookServer::HandleCurveTangent(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveTangent(req, res);
}

void CRookServer::HandleCurveFrame(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveFrame(req, res);
}

void CRookServer::HandleSurfaceNormal(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSurfaceNormal(req, res);
}

void CRookServer::HandleBrepEdges(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBrepEdges(req, res);
}

void CRookServer::HandleBrepFaces(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBrepFaces(req, res);
}

void CRookServer::HandleBrepVertices(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBrepVertices(req, res);
}

void CRookServer::HandleIsClosed(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleIsClosed(req, res);
}

void CRookServer::HandleIsValid(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleIsValid(req, res);
}

// --- Phase 4D: Curves delegates ---

void CRookServer::HandleCurveJoin(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveJoin(req, res);
}

void CRookServer::HandleCurveExplode(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveExplode(req, res);
}

void CRookServer::HandleCurveDivide(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveDivide(req, res);
}

void CRookServer::HandleCurveExtend(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveExtend(req, res);
}

void CRookServer::HandleCurveTrim(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveTrim(req, res);
}

void CRookServer::HandleCurveSplit(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveSplit(req, res);
}

void CRookServer::HandleCurveRebuild(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveRebuild(req, res);
}

void CRookServer::HandleCurveFillet(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveFillet(req, res);
}

void CRookServer::HandleCurveProject(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveProject(req, res);
}

void CRookServer::HandleCurvePull(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurvePull(req, res);
}

void CRookServer::HandleCurveOffset(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveOffset(req, res);
}

void CRookServer::HandleCurveOffsetOnSurface(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCurveOffsetOnSurface(req, res);
}

// --- Phase 4E: Intersection delegates ---

void CRookServer::HandleIntersectCurves(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleIntersectCurves(req, res);
}

void CRookServer::HandleIntersectCurveSurface(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleIntersectCurveSurface(req, res);
}

void CRookServer::HandleIntersectCurveBrep(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleIntersectCurveBrep(req, res);
}

void CRookServer::HandleIntersectBreps(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleIntersectBreps(req, res);
}

void CRookServer::HandleIntersectPlane(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleIntersectPlane(req, res);
}

void CRookServer::HandleRoadIntersectionCandidates(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleRoadIntersectionCandidates(req, res);
}

void CRookServer::HandleRoadIntersectionAnalyze(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleRoadIntersectionAnalyze(req, res);
}

void CRookServer::HandleRoadIntersectionCommit(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleRoadIntersectionCommit(req, res);
}

void CRookServer::HandleRoadIntersectionResolve(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleRoadIntersectionResolve(req, res);
}

// --- Phase 4E: Split/Trim delegates ---

void CRookServer::HandleSplitBrep(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSplitBrep(req, res);
}

void CRookServer::HandleTrimBrep(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleTrimBrep(req, res);
}

void CRookServer::HandleSplitFace(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSplitFace(req, res);
}

// --- Phase 4E: Offset Brep delegate ---

void CRookServer::HandleOffsetBrep(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleOffsetBrep(req, res);
}

// --- Phase 4E: Mesh delegates ---

void CRookServer::HandleMeshFromBrep(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshFromBrep(req, res);
}

void CRookServer::HandleMeshBox(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshBox(req, res);
}

void CRookServer::HandleMeshSphere(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshSphere(req, res);
}

void CRookServer::HandleMeshCylinder(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshCylinder(req, res);
}

void CRookServer::HandleMeshCone(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshCone(req, res);
}

void CRookServer::HandleMeshBoolean(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshBoolean(req, res);
}

void CRookServer::HandleMeshReduce(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshReduce(req, res);
}

void CRookServer::HandleMeshQuadRemesh(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshQuadRemesh(req, res);
}

void CRookServer::HandleMeshRepair(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshRepair(req, res);
}

void CRookServer::HandleMeshSmooth(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshSmooth(req, res);
}

void CRookServer::HandleMeshWeld(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshWeld(req, res);
}

void CRookServer::HandleMeshUnweld(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleMeshUnweld(req, res);
}

// --- Phase 4E: SubD delegates ---

void CRookServer::HandleSubDBox(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSubDBox(req, res);
}

void CRookServer::HandleSubDSphere(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSubDSphere(req, res);
}

void CRookServer::HandleSubDCylinder(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSubDCylinder(req, res);
}

void CRookServer::HandleSubDFromMesh(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSubDFromMesh(req, res);
}

void CRookServer::HandleSubDFromSurface(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSubDFromSurface(req, res);
}

void CRookServer::HandleSubDSubdivide(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSubDSubdivide(req, res);
}

void CRookServer::HandleSubDCrease(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSubDCrease(req, res);
}

void CRookServer::HandleSubDToBrep(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSubDToBrep(req, res);
}

void CRookServer::HandleSubDToMesh(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSubDToMesh(req, res);
}

// --- Phase 4F: Blocks delegates ---

void CRookServer::HandleGetBlocks(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGetBlocks(req, res);
}

void CRookServer::HandleBlockCreate(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockCreate(req, res);
}

void CRookServer::HandleBlockInsert(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockInsert(req, res);
}

void CRookServer::HandleBlockExplode(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockExplode(req, res);
}

void CRookServer::HandleBlockDelete(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockDelete(req, res);
}

void CRookServer::HandleBlockRename(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockRename(req, res);
}

void CRookServer::HandleBlockDescription(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockDescription(req, res);
}

void CRookServer::HandleBlockInfo(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockInfo(req, res);
}

void CRookServer::HandleBlockAddObjects(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockAddObjects(req, res);
}

void CRookServer::HandleBlockRemoveObjects(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockRemoveObjects(req, res);
}

void CRookServer::HandleBlockReplaceGeometry(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockReplaceGeometry(req, res);
}

void CRookServer::HandleBlockInstances(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockInstances(req, res);
}

void CRookServer::HandleBlockReplaceInstance(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockReplaceInstance(req, res);
}

void CRookServer::HandleBlockResetScale(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockResetScale(req, res);
}

void CRookServer::HandleBlockLink(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockLink(req, res);
}

void CRookServer::HandleBlockRefresh(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockRefresh(req, res);
}

void CRookServer::HandleBlockUnlink(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockUnlink(req, res);
}

void CRookServer::HandleBlockPurge(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockPurge(req, res);
}

void CRookServer::HandleBlockDuplicate(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockDuplicate(req, res);
}

void CRookServer::HandleBlockRebase(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockRebase(req, res);
}

void CRookServer::HandleBlockRebaseRecursive(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockRebaseRecursive(req, res);
}

void CRookServer::HandleBlockNested(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockNested(req, res);
}

void CRookServer::HandleBlockCompare(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockCompare(req, res);
}

void CRookServer::HandleBlockMerge(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockMerge(req, res);
}

void CRookServer::HandleBlockLayerCensus(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleBlockLayerCensus(req, res);
}

// --- Phase 4F: Texture Mapping delegates ---

void CRookServer::HandleUvBox(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleUvBox(req, res);
}

void CRookServer::HandleUvPlanar(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleUvPlanar(req, res);
}

void CRookServer::HandleUvCylinder(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleUvCylinder(req, res);
}

void CRookServer::HandleUvSphere(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleUvSphere(req, res);
}

// --- Phase 4F: Game Export delegates ---

void CRookServer::HandleGameExportTag(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGameExportTag(req, res);
}

void CRookServer::HandleGameExportTagFromLayers(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGameExportTagFromLayers(req, res);
}

void CRookServer::HandleGameExportValidate(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGameExportValidate(req, res);
}

void CRookServer::HandleGameExportExport(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGameExportExport(req, res);
}

void CRookServer::HandleGameExportPrepare(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGameExportPrepare(req, res);
}

// --- Phase 3: Scene Graph delegates ---

void CRookServer::HandleSceneGraph(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSceneGraph(req, res);
}

void CRookServer::HandleSceneGraphNode(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSceneGraphNode(req, res);
}

void CRookServer::HandleSceneGraphQuery(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSceneGraphQuery(req, res);
}

void CRookServer::HandleSceneGraphStats(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSceneGraphStats(req, res);
}

void CRookServer::HandleSceneGraphDiff(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSceneGraphDiff(req, res);
}

void CRookServer::HandleSceneGraphReconcile(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSceneGraphReconcile(req, res);
}

void CRookServer::HandleSceneGraphClassify(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSceneGraphClassify(req, res);
}

void CRookServer::HandleSceneGraphOverlay(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSceneGraphOverlay(req, res);
}

// --- Phase 5: Command Interactive delegates ---

void CRookServer::HandleCommandPrompt(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleCommandPrompt(req, res);
}

void CRookServer::HandleCommandStart(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleCommandStart(req, res);
}

void CRookServer::HandleCommandInput(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleCommandInput(req, res);
}

void CRookServer::HandleCommandCancel(const httplib::Request& req, httplib::Response& res)
{
    Rook::McpRequestGuard guard;  // C10: Tag commands as MCP source
    Rook::Handlers::HandleCommandCancel(req, res);
}

// --- Phase 5: User Prompt delegates ---

void CRookServer::HandlePromptPoint(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandlePromptPoint(req, res);
}

void CRookServer::HandlePromptObject(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandlePromptObject(req, res);
}

void CRookServer::HandlePromptObjects(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandlePromptObjects(req, res);
}

void CRookServer::HandlePromptSubObject(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandlePromptSubObject(req, res);
}

void CRookServer::HandlePromptDistance(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandlePromptDistance(req, res);
}

// --- Phase 5: AI Gumball delegates ---

void CRookServer::HandleGumballActivate(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballActivate(req, res);
}

void CRookServer::HandleGumballDeactivate(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballDeactivate(req, res);
}

void CRookServer::HandleGumballStatus(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballStatus(req, res);
}

void CRookServer::HandleGumballHistory(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballHistory(req, res);
}

void CRookServer::HandleGumballSettings(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballSettings(req, res);
}

void CRookServer::HandleGumballExtrude(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballExtrude(req, res);
}

void CRookServer::HandleGumballCut(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballCut(req, res);
}

// --- Phase 6A: AI Gumball v2 delegates ---

void CRookServer::HandleGumballContext(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballContext(req, res);
}

void CRookServer::HandleGumballAlign(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballAlign(req, res);
}

void CRookServer::HandleGumballAppearance(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleGumballAppearance(req, res);
}

// --- Phase 5: Session Recording delegates ---

void CRookServer::HandleSessionCurrent(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSessionCurrent(req, res);
}

void CRookServer::HandleSessionHistory(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSessionHistory(req, res);
}

void CRookServer::HandleSessionList(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSessionList(req, res);
}

void CRookServer::HandleSessionExport(const httplib::Request& req, httplib::Response& res)
{
    Rook::Handlers::HandleSessionExport(req, res);
}
