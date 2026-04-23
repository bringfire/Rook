// ViewportHandler.cpp
//
// POST /viewport — Capture the active viewport to a PNG file.
//
// Approach: Use _-ViewCaptureToFile via RunScript.
// This is simpler and more reliable than CRhinoDib in C++ since
// the command handles all display pipeline setup and file writing.
// The C# version uses view.CaptureToBitmap() (.NET only).
// Always returns a file path (no base64 — the MCP agent reads files directly).

#include "stdafx.h"
#include "Handlers/ViewportHandler.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <filesystem>
#include <chrono>
#include <sstream>
#include <iomanip>

namespace fs = std::filesystem;

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

// Generate a unique filename for the viewport capture.
static std::string GenerateFilename()
{
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;

    std::ostringstream oss;
    oss << "viewport_";

    struct tm tm_buf = {};
    if (localtime_s(&tm_buf, &time) == 0)
    {
        oss << std::put_time(&tm_buf, "%Y%m%d_%H%M%S");
    }
    else
    {
        oss << time;
    }

    oss << "_" << std::setfill('0') << std::setw(3) << ms.count() << ".png";
    return oss.str();
}

// Map standard view name to a Rhino _SetView command.
// Returns empty string if not a standard view name.
static std::wstring ViewNameToCommand(const std::string& viewName)
{
    if (IEquals(viewName, "top"))         return L"_-SetView _World _Top";
    if (IEquals(viewName, "bottom"))      return L"_-SetView _World _Bottom";
    if (IEquals(viewName, "front"))       return L"_-SetView _World _Front";
    if (IEquals(viewName, "back"))        return L"_-SetView _World _Back";
    if (IEquals(viewName, "left"))        return L"_-SetView _World _Left";
    if (IEquals(viewName, "right"))       return L"_-SetView _World _Right";
    if (IEquals(viewName, "perspective")) return L"_-SetView _World _Perspective";
    return {};
}

// ─── POST /viewport ─────────────────────────────────────────────────

void HandleViewport(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // captureBackend discriminator: absent or "legacy" runs the in-process
    // native _-ViewCaptureToFile path; "tier3" dispatches to the managed
    // companion bridge (SDK-backed view.CaptureToBitmap with display-mode
    // resolution and optional raytraced convergence). Any other string is a
    // hard 400 — silent legacy fallback on a misspelling would be a false
    // success that consumers cannot diagnose.
    const std::string captureBackend = body.value("captureBackend", std::string());
    if (!captureBackend.empty()
        && captureBackend != "legacy"
        && captureBackend != "tier3")
    {
        CRookServer::SendError(res,
            "Unknown captureBackend '" + captureBackend +
            "'. Expected 'legacy' or 'tier3' (or omit the field).");
        res.status = 400;
        return;
    }

    if (captureBackend == "tier3")
    {
        // Forward the full request body to the managed Tier 3 handler. The
        // managed side reads documentSerialNumber from the same body and
        // pins the document via DocumentContext.WithDocument, so we do not
        // need to rewrite the payload — just pass it through.
        std::string responseJson;
        int statusCode = 0;
        std::string invokeError;
        const auto invokeResult = InvokeViewportCaptureTier3WithBody(
            req.body.empty() ? body.dump() : req.body,
            responseJson,
            statusCode,
            invokeError);

        switch (invokeResult)
        {
        case ManagedCreateInvokeResult::Ok:
            res.status = statusCode == 0 ? 200 : statusCode;
            res.set_content(responseJson, "application/json");
            res.set_header("X-Rook-Viewport-Backend", "tier3");
            return;
        case ManagedCreateInvokeResult::Unavailable:
            CRookServer::SendError(res,
                "Tier 3 viewport capture requires the Rook companion plugin. "
                "Ensure Rook.rhp is loaded in Rhino, then retry.");
            res.status = 503;
            res.set_header("X-Rook-Viewport-Backend", "tier3-unavailable");
            return;
        case ManagedCreateInvokeResult::Failed:
        default:
            CRookServer::SendError(res,
                "Tier 3 viewport capture failed: " + invokeError);
            res.status = 500;
            res.set_header("X-Rook-Viewport-Backend", "tier3-failed");
            return;
        }
    }

    // Parse parameters (all optional)
    int width = body.value("width", 800);
    int height = body.value("height", 600);
    std::string viewName = body.value("view", "");
    std::string displayMode = body.value("displayMode", "");
    bool zoomExtents = body.value("zoomExtents", false);
    bool transparentBackground = body.value("transparentBackground", false);
    int scale = body.value("scale", 1);
    bool drawGrid = body.value("drawGrid", false);
    bool drawWorldAxes = body.value("drawWorldAxes", false);
    bool drawCPlaneAxes = body.value("drawCPlaneAxes", false);

    // Clamp scale
    scale = (std::max)(1, (std::min)(scale, 10));

    // Clamp dimensions
    width = (std::max)(100, (std::min)(width, 4000));
    height = (std::max)(100, (std::min)(height, 4000));

    // Prepare output path
    fs::path tempDir = fs::temp_directory_path() / "rook" / "viewports";
    std::string filename = GenerateFilename();
    fs::path filePath = tempDir / filename;
    std::string filePathStr = filePath.string();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, width, height, viewName, displayMode, zoomExtents,
         transparentBackground, scale, drawGrid, drawWorldAxes, drawCPlaneAxes,
         filePathStr]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        unsigned int docRuntimeSn = pDoc->RuntimeSerialNumber();

        // Create output directory
        fs::create_directories(fs::path(filePathStr).parent_path());

        CRhinoView* view = pDoc->ActiveView();
        if (!view)
            throw std::runtime_error("No active view available");

        // Save current viewport state for restoration after capture.
        // RunScript commands permanently modify the viewport, so we must
        // restore the full ON_Viewport snapshot after capture.
        CRhinoViewport& vp = view->ActiveViewport();
        ON_Viewport savedVP = vp.VP();  // snapshot entire camera state
        bool viewChanged = false;
        bool displayModeChanged = false;

        std::string actualViewName = WideToUtf8(vp.Name());
        std::string actualDisplayMode = "current";

        // Apply view settings

        // 1. Set view if requested — standard view names or named views
        if (!viewName.empty())
        {
            std::wstring viewCmd = ViewNameToCommand(viewName);
            if (!viewCmd.empty())
            {
                // Standard view (Top, Front, etc.) via RunScript
                RhinoApp().RunScript(docRuntimeSn, viewCmd.c_str(), 0);
                actualViewName = viewName;
                viewChanged = true;
            }
            else
            {
                // Try as a named view — restore via SDK (Tier 1, no RunScript)
                ON_wString wName = Utf8ToWide(viewName);
                int namedViewCount = pDoc->Properties().NamedViewCount();
                int viewIdx = -1;
                for (int i = 0; i < namedViewCount; ++i)
                {
                    const ON_3dmView* pView = pDoc->Properties().NamedView(i);
                    if (pView && pView->m_name.CompareNoCase(wName) == 0)
                    {
                        viewIdx = i;
                        break;
                    }
                }
                if (viewIdx >= 0)
                {
                    const ON_3dmView* pNamedView = pDoc->Properties().NamedView(viewIdx);
                    if (pNamedView)
                    {
                        vp.SetVP(pNamedView->m_vp, true);
                        view->Redraw();
                        actualViewName = viewName;
                        viewChanged = true;
                    }
                }
                // If not found as named view either, silently use current view
            }
        }

        // 2. Set display mode if requested
        if (!displayMode.empty())
        {
            ON_wString wDisplayMode = Utf8ToWide(displayMode);
            std::wstring cmd = L"_-SetDisplayMode " +
                std::wstring(static_cast<const wchar_t*>(wDisplayMode));
            RhinoApp().RunScript(docRuntimeSn, cmd.c_str(), 0);
            actualDisplayMode = displayMode;
            displayModeChanged = true;
        }

        // 3. Zoom extents if requested
        if (zoomExtents)
        {
            RhinoApp().RunScript(docRuntimeSn, L"_-Zoom _All _Extents", 0);
            viewChanged = true;
        }

        // 4. Capture viewport to file using ViewCaptureToFile
        {
            ON_wString wFilePath = Utf8ToWide(filePathStr);
            std::wstring captureCmd = L"_-ViewCaptureToFile \"" +
                std::wstring(static_cast<const wchar_t*>(wFilePath)) +
                L"\" _Width=" + std::to_wstring(width) +
                L" _Height=" + std::to_wstring(height) +
                L" _Scale=" + std::to_wstring(scale) +
                L" _DrawGrid=" + (drawGrid ? L"Yes" : L"No") +
                L" _DrawWorldAxes=" + (drawWorldAxes ? L"Yes" : L"No") +
                L" _DrawCPlaneAxes=" + (drawCPlaneAxes ? L"Yes" : L"No") +
                L" _TransparentBackground=" + (transparentBackground ? L"Yes" : L"No") +
                L" _Enter";

            RhinoApp().RunScript(docRuntimeSn, captureCmd.c_str(), 0);
        }

        // 5. Restore viewport state if we changed it
        if (viewChanged)
        {
            CRhinoViewport& vpRestore = view->ActiveViewport();
            vpRestore.SetVP(savedVP, true);  // restore full camera/projection state
            view->Redraw();
        }

        // Verify the file was created
        if (!fs::exists(filePathStr))
            throw std::runtime_error("Failed to capture viewport");

        nlohmann::json data;
        data["format"] = "png";
        data["width"] = width;
        data["height"] = height;
        data["viewName"] = actualViewName;
        data["displayMode"] = actualDisplayMode;
        data["savedToFile"] = true;
        data["filePath"] = filePathStr;
        data["message"] = "Image saved to file. Use the Read tool to view the image.";
        return data;
    });

    try
    {
        auto data = future.get();
        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
