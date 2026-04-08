// MeshHandler.cpp
//
// 12 mesh routes. Mesh primitives create breps first then mesh them.
// Reduce and QuadRemesh use RunScript (no direct SDK API).
// Boolean, smooth, weld, unweld use Rhino global functions.

#include "stdafx.h"
#include "Handlers/MeshHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/ObjectDiffTracker.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

static const ON_Brep* ExtractBrep(const ON_Geometry* geom, bool& bMustDelete)
{
    bMustDelete = false;

    if (const ON_Brep* brep = ON_Brep::Cast(geom))
        return brep;

    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
    {
        ON_Brep* brep = ext->BrepForm();
        if (brep) { bMustDelete = true; return brep; }
    }

    if (const ON_Surface* srf = ON_Surface::Cast(geom))
    {
        ON_Brep* brep = srf->BrepForm();
        if (brep) { bMustDelete = true; return brep; }
    }

    return nullptr;
}

// Mesh a brep with given parameters, returns a joined mesh (caller owns).
static ON_Mesh* MeshBrep(const ON_Brep& brep, const ON_MeshParameters& mp)
{
    ON_SimpleArray<ON_Mesh*> meshList;
    int count = brep.CreateMesh(mp, meshList);
    if (count == 0 || meshList.Count() == 0)
        return nullptr;

    // Join all face meshes into one
    ON_Mesh* result = meshList[0];
    for (int i = 1; i < meshList.Count(); ++i)
    {
        if (meshList[i])
        {
            result->Append(*meshList[i]);
            delete meshList[i];
        }
    }
    return result;
}

// ─── POST /mesh/from-brep ────────────────────────────────────────

void HandleMeshFromBrep(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID brepId;
    try { brepId = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double density = body.value("density", 0.0);
    double minEdge = body.value("minEdgeLength", 0.0);
    double maxEdge = body.value("maxEdgeLength", 0.0);
    bool jagged = body.value("jagged", false);
    bool simple = body.value("simple", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, brepId, density, minEdge, maxEdge, jagged, simple]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh from brep");

        const CRhinoObject* obj = pDoc->LookupObject(brepId);
        if (!obj)
            throw std::invalid_argument("Brep object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);
        if (!brep)
            throw std::invalid_argument("Object is not a brep/extrusion/surface");

        ON_MeshParameters mp;
        if (simple)
        {
            mp = ON_MeshParameters::FastRenderMesh;
        }
        else
        {
            mp = ON_MeshParameters::QualityRenderMesh;
            if (density > 0.0) mp.SetRelativeTolerance(density);
            if (minEdge > 0.0) mp.SetMinimumEdgeLength(minEdge);
            if (maxEdge > 0.0) mp.SetMaximumEdgeLength(maxEdge);
            mp.SetJaggedSeams(jagged);
        }

        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Meshing failed — geometry may be invalid");

        ON_3dmObjectAttributes attrs = obj->Attributes();
        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh, &attrs);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/box ──────────────────────────────────────────────

void HandleMeshBox(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("width") || !body.contains("depth") || !body.contains("height"))
    {
        CRookServer::SendError(res, "Missing 'width', 'depth', or 'height'");
        return;
    }

    ON_3dPoint origin = ParsePoint3dOrDefault(body, "origin", ON_3dPoint::Origin);
    double width = body["width"].get<double>();
    double depth = body["depth"].get<double>();
    double height = body["height"].get<double>();
    int xCount = body.value("xCount", 1);
    int yCount = body.value("yCount", 1);
    int zCount = body.value("zCount", 1);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, origin, width, depth, height, xCount, yCount, zCount]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh box");

        // Build box from 8 corners, then mesh it
        ON_3dPoint corners[8];
        corners[0] = origin;
        corners[1] = origin + ON_3dVector(width, 0, 0);
        corners[2] = origin + ON_3dVector(width, depth, 0);
        corners[3] = origin + ON_3dVector(0, depth, 0);
        corners[4] = origin + ON_3dVector(0, 0, height);
        corners[5] = origin + ON_3dVector(width, 0, height);
        corners[6] = origin + ON_3dVector(width, depth, height);
        corners[7] = origin + ON_3dVector(0, depth, height);

        ON_Brep* brep = ON_BrepBox(corners);
        if (!brep)
            throw std::invalid_argument("Failed to create box brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Failed to mesh box");

        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/sphere ───────────────────────────────────────────

void HandleMeshSphere(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("radius"))
    {
        CRookServer::SendError(res, "Missing 'radius'");
        return;
    }

    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body["radius"].get<double>();
    int rings = (std::max)(3, body.value("rings", 10));
    int segments = (std::max)(3, body.value("segments", 10));

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, center, radius, rings, segments]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh sphere");

        // Create sphere brep, then mesh with appropriate density
        ON_Sphere sphere(center, radius);
        ON_Brep* brep = ON_BrepSphere(sphere);
        if (!brep)
            throw std::invalid_argument("Failed to create sphere brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        // Adjust mesh params based on rings/segments
        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        mp.SetGridMinCount(rings);
        mp.SetGridMaxCount(segments * rings);

        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Failed to mesh sphere");

        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/cylinder ─────────────────────────────────────────

void HandleMeshCylinder(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("radius") || !body.contains("height"))
    {
        CRookServer::SendError(res, "Missing 'radius' or 'height'");
        return;
    }

    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body["radius"].get<double>();
    double height = body["height"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, center, radius, height]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh cylinder");

        ON_Plane basePlane(center, ON_3dVector::ZAxis);
        ON_Circle circle(basePlane, radius);
        ON_Cylinder cylinder(circle, height);

        ON_Brep* brep = ON_BrepCylinder(cylinder, true, true);
        if (!brep)
            throw std::invalid_argument("Failed to create cylinder brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Failed to mesh cylinder");

        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/cone ─────────────────────────────────────────────

void HandleMeshCone(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("radius") || !body.contains("height"))
    {
        CRookServer::SendError(res, "Missing 'radius' or 'height'");
        return;
    }

    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body["radius"].get<double>();
    double height = body["height"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, center, radius, height]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh cone");

        ON_Plane basePlane(center, ON_3dVector::ZAxis);
        ON_Cone cone(basePlane, height, radius);

        ON_Brep* brep = ON_BrepCone(cone, true);
        if (!brep)
            throw std::invalid_argument("Failed to create cone brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        ON_Mesh* mesh = MeshBrep(*brep, mp);
        if (!mesh)
            throw std::invalid_argument("Failed to mesh cone");

        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int vCount = mesh->VertexCount();
        int fCount = mesh->FaceCount();
        delete mesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/boolean ──────────────────────────────────────────

void HandleMeshBoolean(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("operation") || !body["operation"].is_string())
    {
        CRookServer::SendError(res, "Missing 'operation' (union|difference|intersection)");
        return;
    }

    std::string operation = body["operation"].get<std::string>();
    if (!IEquals(operation, "union") && !IEquals(operation, "difference") &&
        !IEquals(operation, "intersection"))
    {
        CRookServer::SendError(res, "Unknown operation. Use: union, difference, intersection");
        return;
    }

    std::vector<ON_UUID> meshIds;
    try { meshIds = ParseUuids(body, "meshIds"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (meshIds.size() < 2)
    {
        CRookServer::SendError(res, "Need at least 2 mesh IDs");
        return;
    }

    bool deleteInputs = body.value("deleteInputs", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, operation, meshIds = std::move(meshIds), deleteInputs]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Mesh boolean");
        double tol = pDoc->AbsoluteTolerance();

        // Collect mesh pointers
        ON_SimpleArray<const ON_Mesh*> allMeshes;
        for (const auto& uuid : meshIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj)
                throw std::invalid_argument("Mesh not found: " + UuidToString(uuid));
            const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
            if (!mesh)
                throw std::invalid_argument("Object is not a mesh: " + UuidToString(uuid));
            allMeshes.Append(mesh);
        }

        ON_SimpleArray<ON_Mesh*> outMeshes;
        bool happened = false;

        if (IEquals(operation, "union"))
        {
            RhinoMeshBooleanUnion(allMeshes, tol, tol, &happened, outMeshes);
        }
        else
        {
            // Difference and intersection: first mesh vs rest
            ON_SimpleArray<const ON_Mesh*> set0, set1;
            set0.Append(allMeshes[0]);
            for (int i = 1; i < allMeshes.Count(); ++i)
                set1.Append(allMeshes[i]);

            if (IEquals(operation, "difference"))
                RhinoMeshBooleanDifference(set0, set1, tol, tol, &happened, outMeshes);
            else
                RhinoMeshBooleanIntersection(set0, set1, tol, tol, &happened, outMeshes);
        }

        if (!happened || outMeshes.Count() == 0)
        {
            for (int i = 0; i < outMeshes.Count(); ++i)
                delete outMeshes[i];

            WriteResult wr;
            wr.success = false;
            wr.data["error"] = "Mesh boolean " + operation + " produced no result";
            return wr;
        }

        nlohmann::json resultIds = nlohmann::json::array();
        for (int i = 0; i < outMeshes.Count(); ++i)
        {
            if (outMeshes[i])
            {
                CRhinoMeshObject* newObj = pDoc->AddMeshObject(*outMeshes[i]);
                if (newObj)
                    resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
                delete outMeshes[i];
                outMeshes[i] = nullptr;
            }
        }

        if (deleteInputs)
        {
            for (const auto& uuid : meshIds)
            {
                const CRhinoObject* obj = pDoc->LookupObject(uuid);
                if (obj)
                    pDoc->DeleteObject(CRhinoObjRef(obj));
            }
        }

        WriteResult wr;
        wr.success = true;
        wr.data["operation"] = operation;
        wr.data["resultCount"] = static_cast<int>(resultIds.size());
        wr.data["resultIds"] = std::move(resultIds);

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/reduce ───────────────────────────────────────────

void HandleMeshReduce(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("targetCount") || !body["targetCount"].is_number_integer())
    {
        CRookServer::SendError(res, "Missing 'targetCount' integer");
        return;
    }

    int targetCount = body["targetCount"].get<int>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, targetCount]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Reduce mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        int originalFaces = mesh->FaceCount();

        // Select the mesh and use RunScript (no direct API for mesh reduce)
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);

        const_cast<CRhinoObject*>(obj)->Select(true);

        ON_wString cmd;
        cmd.Format(L"_-ReduceMesh _PolygonCount=%d _Enter _Enter", targetCount);

        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(cmd), 0);

        // Re-fetch: command may modify in-place (same UUID) or create new object
        ON_UUID resultId = meshId;
        const CRhinoObject* newObj = pDoc->LookupObject(meshId);
        if (!newObj)
        {
            // UUID changed — find by diff tracker would be ideal but
            // ReduceMesh almost always modifies in-place. Fall back to error.
            throw std::invalid_argument("Mesh was deleted during reduce");
        }

        const ON_Mesh* newMesh = ON_Mesh::Cast(newObj->Geometry());
        if (!newMesh)
            throw std::invalid_argument("Object is no longer a mesh after reduce");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["originalFaceCount"] = originalFaces;
        wr.data["newFaceCount"] = newMesh->FaceCount();
        wr.data["vertexCount"] = newMesh->VertexCount();

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/quad-remesh ──────────────────────────────────────

void HandleMeshQuadRemesh(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    int targetQuadCount = body.value("targetQuadCount", 1000);
    bool adaptive = body.value("adaptive", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, targetQuadCount, adaptive]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"QuadRemesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        // Use RunScript (no direct QuadRemesh API in C++ SDK)
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);

        const_cast<CRhinoObject*>(obj)->Select(true);

        ON_wString cmd;
        const wchar_t* adaptiveStr = adaptive ? L"Yes" : L"No";
        cmd.Format(L"_-QuadRemesh _TargetQuadCount=%d _AdaptiveQuadCount=%s _Enter",
                   targetQuadCount, adaptiveStr);

        ObjectDiffTracker tracker(pDoc);
        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(cmd), 0);

        std::vector<ON_UUID> newIds = tracker.GetNewObjects();

        // If we got new objects, the original was replaced
        ON_UUID resultId = meshId;
        int fCount = 0, vCount = 0;

        if (!newIds.empty())
        {
            resultId = newIds[0];
            const CRhinoObject* newObj = pDoc->LookupObject(resultId);
            if (newObj)
            {
                const ON_Mesh* newMesh = ON_Mesh::Cast(newObj->Geometry());
                if (newMesh) { fCount = newMesh->FaceCount(); vCount = newMesh->VertexCount(); }
            }
        }
        else
        {
            // Original may have been modified in-place
            const CRhinoObject* reObj = pDoc->LookupObject(meshId);
            if (reObj)
            {
                const ON_Mesh* reMesh = ON_Mesh::Cast(reObj->Geometry());
                if (reMesh) { fCount = reMesh->FaceCount(); vCount = reMesh->VertexCount(); }
            }
        }

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["faceCount"] = fCount;
        wr.data["vertexCount"] = vCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/repair ───────────────────────────────────────────

void HandleMeshRepair(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    bool fillHoles = body.value("fillHoles", true);
    bool rebuildNormals = body.value("rebuildNormals", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, fillHoles, rebuildNormals]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Repair mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        ON_Mesh* newMesh = new ON_Mesh(*mesh);
        if (!newMesh)
            throw std::invalid_argument("Failed to duplicate mesh");

        nlohmann::json repairs = nlohmann::json::array();

        // Repair using RhinoRepairMesh
        double tol = pDoc->AbsoluteTolerance();
        if (RhinoRepairMesh(newMesh, tol))
            repairs.push_back("Repaired mesh");

        if (rebuildNormals)
        {
            newMesh->ComputeVertexNormals();
            repairs.push_back("Rebuilt normals");
        }

        // Unify normals
        ON_Mesh* unified = RhinoUnifyMeshNormals(*newMesh);
        if (unified && unified != newMesh)
        {
            delete newMesh;
            newMesh = unified;
            repairs.push_back("Unified normals");
        }
        else if (unified == newMesh)
        {
            repairs.push_back("Normals already unified");
        }

        newMesh->Compact();
        repairs.push_back("Compacted mesh");

        pDoc->ReplaceObject(CRhinoObjRef(obj), *newMesh);
        int vCount = newMesh->VertexCount();
        int fCount = newMesh->FaceCount();
        bool isValid = newMesh->IsValid();
        delete newMesh;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(meshId);
        wr.data["repairs"] = std::move(repairs);
        wr.data["faceCount"] = fCount;
        wr.data["vertexCount"] = vCount;
        wr.data["isValid"] = isValid;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/smooth ───────────────────────────────────────────

void HandleMeshSmooth(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double factor = body.value("factor", 0.5);
    factor = (std::max)(0.0, (std::min)(1.0, factor));
    int iterations = body.value("iterations", 1);
    iterations = (std::max)(1, (std::min)(100, iterations));

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, factor, iterations]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Smooth mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        // RhinoSmoothMesh with numSteps
        ON_Mesh* smoothed = RhinoSmoothMesh(mesh, factor, iterations,
            true, true, true,  // x, y, z smoothing
            true,              // fix boundaries
            0,                 // world coordinate system
            nullptr);          // no custom plane

        if (!smoothed)
            throw std::invalid_argument("Mesh smoothing failed");

        pDoc->ReplaceObject(CRhinoObjRef(obj), *smoothed);
        int vCount = smoothed->VertexCount();
        int fCount = smoothed->FaceCount();
        delete smoothed;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(meshId);
        wr.data["factor"] = factor;
        wr.data["iterations"] = iterations;
        wr.data["vertexCount"] = vCount;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/weld ─────────────────────────────────────────────

void HandleMeshWeld(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double angleDegrees = body.value("angle", 22.5);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, angleDegrees]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Weld mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        int origVerts = mesh->VertexCount();

        // ON_Mesh::Weld() doesn't exist in SDK; use RunScript
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);
        const_cast<CRhinoObject*>(obj)->Select(true);

        ON_wString cmd;
        cmd.Format(L"_-Weld _Angle=%g _Enter", angleDegrees);
        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(cmd), 0);

        // Re-fetch (object may have been replaced)
        const CRhinoObject* newObj = pDoc->LookupObject(meshId);
        const ON_Mesh* newMesh = newObj ? ON_Mesh::Cast(newObj->Geometry()) : nullptr;
        int newVerts = newMesh ? newMesh->VertexCount() : origVerts;
        int fCount = newMesh ? newMesh->FaceCount() : 0;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(meshId);
        wr.data["angle"] = angleDegrees;
        wr.data["originalVertexCount"] = origVerts;
        wr.data["newVertexCount"] = newVerts;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /mesh/unweld ───────────────────────────────────────────

void HandleMeshUnweld(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double angleDegrees = body.value("angle", 22.5);
    double angleRadians = angleDegrees * ON_PI / 180.0;

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId, angleDegrees, angleRadians]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Unweld mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        int origVerts = mesh->VertexCount();

        ON_Mesh* unwelded = RhinoUnWeldMesh(*mesh, angleRadians);
        if (!unwelded)
            throw std::invalid_argument("Unweld failed");

        pDoc->ReplaceObject(CRhinoObjRef(obj), *unwelded);
        int newVerts = unwelded->VertexCount();
        int fCount = unwelded->FaceCount();
        delete unwelded;

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(meshId);
        wr.data["angle"] = angleDegrees;
        wr.data["originalVertexCount"] = origVerts;
        wr.data["newVertexCount"] = newVerts;
        wr.data["faceCount"] = fCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
