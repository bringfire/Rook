// DocumentOpsHandler.cpp
//
// POST /document/open       — Open an existing .3dm file
// POST /document/save       — Save document to disk
// POST /document/save-copy  — Write a copy without retargeting the document
// POST /document/new        — Create new document
// POST /document/units   — Change model units
// GET  /views            — List named views
// POST /views/save       — Save current viewport as named view
// POST /views/restore    — Restore a named view

#include "stdafx.h"
#include "Handlers/DocumentOpsHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/PathValidation.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

// Map a unit name string (case-insensitive) to ON::LengthUnitSystem.
// Returns ON::LengthUnitSystem::None if unrecognized.
static ON::LengthUnitSystem ParseUnitSystem(const std::string& name)
{
    if (IEquals(name, "millimeters") || IEquals(name, "mm"))
        return ON::LengthUnitSystem::Millimeters;
    if (IEquals(name, "centimeters") || IEquals(name, "cm"))
        return ON::LengthUnitSystem::Centimeters;
    if (IEquals(name, "meters") || IEquals(name, "m"))
        return ON::LengthUnitSystem::Meters;
    if (IEquals(name, "kilometers") || IEquals(name, "km"))
        return ON::LengthUnitSystem::Kilometers;
    if (IEquals(name, "inches") || IEquals(name, "in"))
        return ON::LengthUnitSystem::Inches;
    if (IEquals(name, "feet") || IEquals(name, "ft"))
        return ON::LengthUnitSystem::Feet;
    if (IEquals(name, "yards") || IEquals(name, "yd"))
        return ON::LengthUnitSystem::Yards;
    if (IEquals(name, "miles") || IEquals(name, "mi"))
        return ON::LengthUnitSystem::Miles;
    if (IEquals(name, "microinches"))
        return ON::LengthUnitSystem::Microinches;
    if (IEquals(name, "mils"))
        return ON::LengthUnitSystem::Mils;
    if (IEquals(name, "microns") || IEquals(name, "micrometers"))
        return ON::LengthUnitSystem::Microns;
    if (IEquals(name, "nanometers"))
        return ON::LengthUnitSystem::Nanometers;
    if (IEquals(name, "angstroms"))
        return ON::LengthUnitSystem::Angstroms;
    if (IEquals(name, "decimeters"))
        return ON::LengthUnitSystem::Decimeters;
    return ON::LengthUnitSystem::None;
}

static std::string UnitSystemToString(ON::LengthUnitSystem units)
{
    switch (units)
    {
    case ON::LengthUnitSystem::Millimeters:  return "Millimeters";
    case ON::LengthUnitSystem::Centimeters:  return "Centimeters";
    case ON::LengthUnitSystem::Meters:       return "Meters";
    case ON::LengthUnitSystem::Kilometers:   return "Kilometers";
    case ON::LengthUnitSystem::Inches:       return "Inches";
    case ON::LengthUnitSystem::Feet:         return "Feet";
    case ON::LengthUnitSystem::Yards:        return "Yards";
    case ON::LengthUnitSystem::Miles:        return "Miles";
    case ON::LengthUnitSystem::Microinches:  return "Microinches";
    case ON::LengthUnitSystem::Mils:         return "Mils";
    case ON::LengthUnitSystem::Microns:      return "Microns";
    case ON::LengthUnitSystem::Nanometers:   return "Nanometers";
    case ON::LengthUnitSystem::Angstroms:    return "Angstroms";
    case ON::LengthUnitSystem::Decimeters:   return "Decimeters";
    default:                                 return "Unknown";
    }
}

// ─── POST /document/open ────────────────────────────────────────────

void HandleDocumentOpen(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("path") || !body["path"].is_string())
    {
        CRookServer::SendError(res, "Missing required parameter 'path'");
        return;
    }

    std::string filePath = body["path"].get<std::string>();

    std::string pathErr = Rook::ValidateFilePath(filePath);
    if (!pathErr.empty())
    {
        CRookServer::SendError(res, pathErr);
        return;
    }

    // Verify file exists before attempting open (benign TOCTOU — Rhino handles missing files gracefully)
    ON_wString widePath = Utf8ToWide(filePath);
    if (!ON_FileSystem::PathExists(static_cast<const wchar_t*>(widePath)))
    {
        CRookServer::SendError(res, "File not found: " + filePath);
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, filePath]() -> WriteResult
    {
        ON_wString widePath = Utf8ToWide(filePath);

        // Capture current doc BEFORE open — used to detect whether open actually changed the doc
        CRhinoDoc* pOldDoc = RhinoApp().ActiveDoc();
        unsigned int oldSn = pOldDoc ? pOldDoc->RuntimeSerialNumber() : 0;

        // Mark current doc as unmodified to suppress "Save changes?" dialog,
        // which would block the main thread indefinitely in scripted mode.
        if (pOldDoc)
            pOldDoc->SetModifiedFlag(false);

        // _-Open in scripted mode opens the file without the file-selection dialog
        ON_wString script = L"_-Open \"";
        script += widePath;
        script += L"\"";

        RhinoApp().RunScript(pOldDoc ? pOldDoc->RuntimeSerialNumber()
                                     : CRhinoDoc::NullRuntimeSerialNumber,
                             static_cast<const wchar_t*>(script), 0);

        // After RunScript, check if the active doc actually changed
        CRhinoDoc* pNewDoc = RhinoApp().ActiveDoc();

        // Count active (non-deleted) objects in a document
        auto countObjects = [](CRhinoDoc* pDoc) -> int {
            CRhinoObjectIterator it(pDoc->RuntimeSerialNumber(), CRhinoObjectIterator::undeleted_objects);
            it.IncludeLights(false);
            int count = 0;
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
                ++count;
            return count;
        };

        WriteResult wr;
        if (!pNewDoc)
        {
            wr.success = false;
            wr.error = "Failed to open file — no active document after RunScript";
        }
        else if (pNewDoc->RuntimeSerialNumber() == oldSn && oldSn != 0)
        {
            // Active doc didn't change — open may have failed (corrupted file, wrong format, etc.)
            // Report success=false unless the old doc's path matches the requested path
            // (which would mean the file was already open)
            ON_wString currentPath = pNewDoc->GetPathName();
            ON_wString requestedPath = Utf8ToWide(filePath);
            if (currentPath.CompareNoCase(requestedPath) == 0)
            {
                // File was already open — this is fine
                wr.success = true;
                wr.data["name"] = WideToUtf8(pNewDoc->GetTitle());
                const ON_3dmUnitsAndTolerances& ut = pNewDoc->Properties().ModelUnitsAndTolerances();
                wr.data["units"] = WideToUtf8(ut.m_unit_system.ToString());
                wr.data["objectCount"] = countObjects(pNewDoc);
                wr.data["path"] = filePath;
                wr.data["alreadyOpen"] = true;
            }
            else
            {
                wr.success = false;
                wr.error = "Open command did not change the active document — file may be corrupted or invalid";
            }
        }
        else
        {
            wr.success = true;
            wr.data["name"] = WideToUtf8(pNewDoc->GetTitle());
            const ON_3dmUnitsAndTolerances& ut = pNewDoc->Properties().ModelUnitsAndTolerances();
            wr.data["units"] = WideToUtf8(ut.m_unit_system.ToString());
            wr.data["objectCount"] = countObjects(pNewDoc);
            wr.data["path"] = filePath;
        }
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /document/save ────────────────────────────────────────────

void HandleDocumentSave(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string path;
    if (body.contains("path") && body["path"].is_string())
        path = body["path"].get<std::string>();

    if (!path.empty())
    {
        std::string pathErr = Rook::ValidateFilePath(path);
        if (!pathErr.empty())
        {
            CRookServer::SendError(res, pathErr);
            return;
        }
    }

    bool saveSmall = body.value("small", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, path, saveSmall]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        ON_wString savePath;
        if (!path.empty())
        {
            savePath = Utf8ToWide(path);
        }
        else
        {
            savePath = pDoc->GetPathName();
            if (savePath.IsEmpty())
                throw std::invalid_argument("No path provided and document has no existing path");
        }

        CRhinoFileWriteOptions opts;
        opts.SetFileName(static_cast<const wchar_t*>(savePath));

        if (saveSmall)
            opts.SetIncludeRenderMeshes(false);

        if (!pDoc->WriteFile(opts))
            throw std::runtime_error("Failed to save document");

        WriteResult wr;
        wr.success = true;
        wr.data["path"] = WideToUtf8(savePath);
        wr.data["small"] = saveSmall;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /document/save-copy ───────────────────────────────────────
// Writes the active document to a target path WITHOUT retargeting the
// document, changing its modified flag, or touching its undo stack.
// SDK contract: CRhinoFileWriteOptions::SetUpdateDocumentPath(false) =>
// "The document's default file path, title and modified state will not
// be changed under any circumstances." Render meshes stay included.

void HandleDocumentSaveCopy(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string path;
    if (body.contains("path") && body["path"].is_string())
        path = body["path"].get<std::string>();

    if (path.empty())
    {
        CRookServer::SendError(res, "Missing required parameter 'path'");
        return;
    }

    std::string pathErr = Rook::ValidateFilePath(path);
    if (!pathErr.empty())
    {
        CRookServer::SendError(res, pathErr);
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, path]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const ON_wString pathBefore = pDoc->GetPathName();
        const ON_wString titleBefore = pDoc->GetTitle();
        const bool modifiedBefore = pDoc->IsModified();

        ON_wString copyPath = Utf8ToWide(path);

        CRhinoFileWriteOptions opts;
        opts.SetFileName(static_cast<const wchar_t*>(copyPath));
        opts.SetUpdateDocumentPath(false);
        opts.SetUseBatchMode(true);
        // Render meshes: default is included; never SetIncludeRenderMeshes(false) here.

        if (!pDoc->WriteFile(opts))
            throw std::runtime_error("save-copy write failed");

        WriteResult wr;
        wr.success = true;
        wr.data["copy_path"] = path;
        wr.data["path_before"] = WideToUtf8(pathBefore);
        wr.data["path_after"] = WideToUtf8(pDoc->GetPathName());
        wr.data["title_before"] = WideToUtf8(titleBefore);
        wr.data["title_after"] = WideToUtf8(pDoc->GetTitle());
        wr.data["modified_before"] = modifiedBefore;
        wr.data["modified_after"] = pDoc->IsModified();
        wr.data["save_small_used"] = false;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /document/new ─────────────────────────────────────────────

void HandleDocumentNew(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string templateName;
    if (body.contains("template") && body["template"].is_string())
        templateName = body["template"].get<std::string>();

    // Reject template names containing quotes — prevents RunScript command injection
    if (templateName.find('"') != std::string::npos)
    {
        CRookServer::SendError(res, "Template name cannot contain quotes");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, templateName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        // Build the RunScript command
        // _-New _None creates a blank doc; _-New "template.3dm" uses a template
        ON_wString script;
        if (templateName.empty())
        {
            script = L"_-New _None";
        }
        else
        {
            ON_wString tmpl = Utf8ToWide(templateName);
            // If user didn't include .3dm extension, add it
            if (tmpl.Find(L".3dm") == -1)
                tmpl += L".3dm";
            script = L"_-New \"";
            script += tmpl;
            script += L"\"";
        }

        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), static_cast<const wchar_t*>(script), 0);

        // After RunScript, the active doc may have changed
        CRhinoDoc* pNewDoc = RhinoApp().ActiveDoc();

        WriteResult wr;
        wr.success = true;
        if (pNewDoc)
        {
            wr.data["name"] = WideToUtf8(pNewDoc->GetTitle());
            const ON_3dmUnitsAndTolerances& ut = pNewDoc->Properties().ModelUnitsAndTolerances();
            wr.data["units"] = WideToUtf8(ut.m_unit_system.ToString());
        }
        else
        {
            wr.data["name"] = "Untitled";
            wr.data["units"] = "Unknown";
        }
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /document/units ───────────────────────────────────────────

void HandleDocumentUnits(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("units") || !body["units"].is_string())
    {
        CRookServer::SendError(res, "Missing 'units' field (string)");
        return;
    }

    std::string unitsStr = body["units"].get<std::string>();
    bool scale = body.value("scale", false);

    ON::LengthUnitSystem newUnits = ParseUnitSystem(unitsStr);
    if (newUnits == ON::LengthUnitSystem::None)
    {
        CRookServer::SendError(res, "Unrecognized unit system: " + unitsStr);
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, newUnits, scale]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Change Units");

        const ON_3dmUnitsAndTolerances& curUt = pDoc->Properties().ModelUnitsAndTolerances();
        ON::LengthUnitSystem oldUnits = curUt.m_unit_system.UnitSystem();
        std::string prevStr = UnitSystemToString(oldUnits);

        if (scale && oldUnits != newUnits)
        {
            double scaleFactor = ON::UnitScale(oldUnits, newUnits);

            ON_Xform xform = ON_Xform::ScaleTransformation(ON_3dPoint::Origin, scaleFactor);

            // Collect all objects first — TransformObject(bDeleteOriginal=true)
            // mutates the document's object table, which invalidates the
            // iterator if done during iteration.
            std::vector<const CRhinoObject*> objects;
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
                objects.push_back(obj);

            for (const CRhinoObject* obj : objects)
                pDoc->TransformObject(obj, xform, true, true, true);
        }

        // Set the new unit system
        ON_3dmUnitsAndTolerances ut = pDoc->Properties().ModelUnitsAndTolerances();
        ut.m_unit_system = ON_UnitSystem(newUnits);
        pDoc->Properties().SetModelUnitsAndTolerances(ut, true);

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["previousUnits"] = prevStr;
        wr.data["newUnits"] = UnitSystemToString(newUnits);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── GET /views ─────────────────────────────────────────────────────

void HandleGetViews(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        nlohmann::json views = nlohmann::json::array();
        int count = pDoc->Properties().NamedViewCount();

        for (int i = 0; i < count; ++i)
        {
            const ON_3dmView* pView = pDoc->Properties().NamedView(i);
            if (!pView) continue;

            nlohmann::json v;
            v["name"] = WideToUtf8(pView->m_name);
            v["index"] = i;
            views.push_back(std::move(v));
        }

        nlohmann::json result;
        result["count"] = static_cast<int>(views.size());
        result["views"] = std::move(views);
        return result;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /views/save ───────────────────────────────────────────────

void HandleViewsSave(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field (string)");
        return;
    }

    std::string viewName = body["name"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, viewName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        CRhinoView* pActiveView = pDoc->ActiveView();
        if (!pActiveView)
            throw std::runtime_error("No active view");

        // Capture current viewport state as named view
        ON_3dmView namedView;
        namedView.m_name = Utf8ToWide(viewName);
        namedView.m_vp = pActiveView->ActiveViewport().VP();

        int idx = pDoc->Properties().AddNamedView(namedView);
        if (idx < 0)
            throw std::runtime_error("Failed to save named view");

        WriteResult wr;
        wr.success = true;
        wr.data["name"] = viewName;
        wr.data["index"] = idx;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /views/restore ────────────────────────────────────────────

void HandleViewsRestore(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field (string)");
        return;
    }

    std::string viewName = body["name"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, viewName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        // Find named view by name
        ON_wString wName = Utf8ToWide(viewName);
        int viewIdx = -1;
        int count = pDoc->Properties().NamedViewCount();
        for (int i = 0; i < count; ++i)
        {
            const ON_3dmView* pView = pDoc->Properties().NamedView(i);
            if (pView && pView->m_name.CompareNoCase(wName) == 0)
            {
                viewIdx = i;
                break;
            }
        }

        if (viewIdx < 0)
            throw std::invalid_argument("Named view '" + viewName + "' not found");

        const ON_3dmView* pNamedView = pDoc->Properties().NamedView(viewIdx);
        if (!pNamedView)
            throw std::runtime_error("Failed to retrieve named view");

        CRhinoView* pActiveView = pDoc->ActiveView();
        if (!pActiveView)
            throw std::runtime_error("No active view");

        // Apply the named view's viewport settings
        pActiveView->ActiveViewport().SetVP(pNamedView->m_vp, true);
        pActiveView->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["name"] = viewName;
        wr.data["restored"] = true;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
