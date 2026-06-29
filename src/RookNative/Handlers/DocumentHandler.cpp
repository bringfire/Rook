// DocumentHandler.cpp
//
// GET /document — returns document metadata.

#include "stdafx.h"
#include "Handlers/DocumentHandler.h"
#include "Models/Snapshots.h"
#include "Models/DocumentHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <mutex>
#include <unordered_map>

namespace Rook {
namespace Handlers {
namespace {

std::string DocumentSessionIdForRuntimeSerial(unsigned int runtimeSerial)
{
    static std::mutex sessionIdsMutex;
    static std::unordered_map<unsigned int, std::string> sessionIdsByRuntimeSerial;

    std::lock_guard<std::mutex> lock(sessionIdsMutex);
    auto existing = sessionIdsByRuntimeSerial.find(runtimeSerial);
    if (existing != sessionIdsByRuntimeSerial.end())
        return existing->second;

    ON_UUID sessionUuid = ON_nil_uuid;
    if (FAILED(CoCreateGuid(&sessionUuid)))
        throw std::runtime_error("Could not allocate document session id");

    sessionIdsByRuntimeSerial[runtimeSerial] = UuidToString(sessionUuid);
    return sessionIdsByRuntimeSerial[runtimeSerial];
}

} // namespace

void HandleDocument(const httplib::Request& req, httplib::Response& res)
{
    // Parse documentSerialNumber from query params or body
    unsigned int docSn = 0;
    if (req.has_param("documentSerialNumber"))
    {
        try { docSn = static_cast<unsigned int>(std::stoul(req.get_param_value("documentSerialNumber"))); }
        catch (...) {}
    }
    if (docSn == 0 && !req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.contains("documentSerialNumber"))
            docSn = body.value("documentSerialNumber", 0u);
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch([docSn]() -> DocumentSnapshot
    {
        // Resolve document (cannot use thread-local g_request_doc_serial across threads)
        CRhinoDoc* pDoc = nullptr;
        if (docSn > 0)
            pDoc = CRhinoDoc::FromRuntimeSerialNumber(docSn);
        if (!pDoc)
            pDoc = GetDocument();
        if (!pDoc)
            throw std::runtime_error("No active document");

        DocumentSnapshot snap;
        snap.documentSessionId = DocumentSessionIdForRuntimeSerial(pDoc->RuntimeSerialNumber());

        // Name — use the title, fall back to "Untitled"
        ON_wString title = pDoc->GetTitle();
        snap.name = WideToUtf8(title);
        if (snap.name.empty())
            snap.name = "Untitled";

        snap.path = WideToUtf8(pDoc->GetPathName());
        snap.isSaved = !snap.path.empty();

        // Unit system
        const ON_3dmUnitsAndTolerances& ut = pDoc->Properties().ModelUnitsAndTolerances();
        ON_wString unitName = ut.m_unit_system.ToString();
        snap.units = WideToUtf8(unitName);

        snap.tolerance = ut.m_absolute_tolerance;
        // Rhino stores angle tolerance in radians; C# returns degrees
        snap.angleTolerance = RoundTo(ut.m_angle_tolerance * (180.0 / ON_PI), 2);

        // Object count — iterate to count non-deleted
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            int count = 0;
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
                ++count;
            snap.objectCount = count;
        }

        // Layer count (excluding deleted)
        int layerCount = 0;
        for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
        {
            if (!pDoc->m_layer_table[i].IsDeleted())
                ++layerCount;
        }
        snap.layerCount = layerCount;

        // Active layer
        int curIdx = pDoc->m_layer_table.CurrentLayerIndex();
        if (curIdx >= 0 && curIdx < pDoc->m_layer_table.LayerCount())
        {
            ON_wString layerPath;
            pDoc->m_layer_table.GetLayerPathName(curIdx, layerPath);
            snap.activeLayer = WideToUtf8(layerPath);
        }
        else
        {
            snap.activeLayer = "Default";
        }

        snap.modified = pDoc->IsModified();

        return snap;
    });

    try
    {
        auto snapshot = future.get();
        CRookServer::SendSuccess(res, Serializer::SerializeDocument(snapshot));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
