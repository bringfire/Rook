// SubDHandler.cpp
//
// 9 SubD routes. SubD primitives create meshes first then convert via
// ON_SubD::CreateFromMesh. Conversion routes use ON_SubDToBrepParameters.

#include "stdafx.h"
#include "Handlers/SubDHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
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

// Create a mesh box from dimensions (ON_Mesh::CreateMeshBox doesn't exist).
static ON_Mesh* CreateMeshBox(const ON_3dPoint& origin, double w, double d, double h,
                               int xFaces, int yFaces, int zFaces)
{
    // Create box brep, then mesh it
    ON_3dPoint corners[8];
    corners[0] = origin;
    corners[1] = origin + ON_3dVector(w, 0, 0);
    corners[2] = origin + ON_3dVector(w, d, 0);
    corners[3] = origin + ON_3dVector(0, d, 0);
    corners[4] = origin + ON_3dVector(0, 0, h);
    corners[5] = origin + ON_3dVector(w, 0, h);
    corners[6] = origin + ON_3dVector(w, d, h);
    corners[7] = origin + ON_3dVector(0, d, h);

    ON_Brep* brep = ON_BrepBox(corners);
    if (!brep) return nullptr;
    std::unique_ptr<ON_Brep> brepGuard(brep);

    ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
    ON_SimpleArray<ON_Mesh*> meshList;
    brep->CreateMesh(mp, meshList);
    if (meshList.Count() == 0) return nullptr;

    ON_Mesh* result = meshList[0];
    for (int i = 1; i < meshList.Count(); ++i)
    {
        if (meshList[i]) { result->Append(*meshList[i]); delete meshList[i]; }
    }
    return result;
}

// Add ON_SubD to document using CRhinoSubDObject::AddToDocument.
// Creates a managed copy via ON_SubDRef. Caller still owns the original pointer.
static ON_UUID AddSubDToDocument(CRhinoDoc* pDoc, const ON_SubD& subd)
{
    ON_SubDRef subdRef = ON_SubDRef::CreateReferenceForExperts(subd);
    unsigned int objSn = CRhinoSubDObject::AddToDocument(subdRef, pDoc->RuntimeSerialNumber());
    if (objSn == 0)
        return ON_nil_uuid;

    // Find UUID by runtime serial number
    CRhinoObjectIterator it(*pDoc,
        CRhinoObjectIterator::normal_objects,
        CRhinoObjectIterator::active_objects);
    for (const CRhinoObject* o = it.First(); o; o = it.Next())
    {
        if (o->RuntimeSerialNumber() == objSn)
            return o->Attributes().m_uuid;
    }
    return ON_nil_uuid;
}

// ─── POST /subd/box ──────────────────────────────────────────────

void HandleSubDBox(const httplib::Request& req, httplib::Response& res)
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
    int xFaces = body.value("xFaces", 2);
    int yFaces = body.value("yFaces", 2);
    int zFaces = body.value("zFaces", 2);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, origin, width, depth, height, xFaces, yFaces, zFaces]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"SubD box");

        ON_Mesh* mesh = CreateMeshBox(origin, width, depth, height, xFaces, yFaces, zFaces);
        if (!mesh)
            throw std::invalid_argument("Failed to create mesh for SubD box");
        std::unique_ptr<ON_Mesh> meshGuard(mesh);

        ON_SubD* subd = ON_SubD::CreateFromMesh(mesh, nullptr, nullptr);
        if (!subd)
            throw std::invalid_argument("Failed to create SubD from mesh");
        std::unique_ptr<ON_SubD> subdGuard(subd);

        int fc = static_cast<int>(subd->FaceCount());
        int ec = static_cast<int>(subd->EdgeCount());
        int vc = static_cast<int>(subd->VertexCount());

        ON_UUID resultId = AddSubDToDocument(pDoc, *subd);
        if (ON_UuidIsNil(resultId))
            throw std::invalid_argument("Failed to add SubD to document");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["faceCount"] = fc;
        wr.data["edgeCount"] = ec;
        wr.data["vertexCount"] = vc;

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

// ─── POST /subd/sphere ──────────────────────────────────────────

void HandleSubDSphere(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("radius"))
    {
        CRookServer::SendError(res, "Missing 'radius'");
        return;
    }

    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body["radius"].get<double>();
    int divisions = body.value("divisions", 3);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, center, radius, divisions]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"SubD sphere");

        // Create sphere brep → mesh → SubD
        ON_Sphere sphere(center, radius);
        ON_Brep* brep = ON_BrepSphere(sphere);
        if (!brep)
            throw std::invalid_argument("Failed to create sphere brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        mp.SetGridMinCount(divisions * 4);
        mp.SetGridMaxCount(divisions * 4 * divisions * 4);

        ON_SimpleArray<ON_Mesh*> meshList;
        brep->CreateMesh(mp, meshList);
        if (meshList.Count() == 0)
            throw std::invalid_argument("Failed to mesh sphere");

        ON_Mesh* mesh = meshList[0];
        for (int i = 1; i < meshList.Count(); ++i)
        {
            if (meshList[i]) { mesh->Append(*meshList[i]); delete meshList[i]; }
        }
        std::unique_ptr<ON_Mesh> meshGuard(mesh);

        ON_SubD* subd = ON_SubD::CreateFromMesh(mesh, nullptr, nullptr);
        if (!subd)
            throw std::invalid_argument("Failed to create SubD from mesh");
        std::unique_ptr<ON_SubD> subdGuard(subd);

        int fc = static_cast<int>(subd->FaceCount());
        int ec = static_cast<int>(subd->EdgeCount());
        int vc = static_cast<int>(subd->VertexCount());

        ON_UUID resultId = AddSubDToDocument(pDoc, *subd);
        if (ON_UuidIsNil(resultId))
            throw std::invalid_argument("Failed to add SubD to document");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["faceCount"] = fc;
        wr.data["edgeCount"] = ec;
        wr.data["vertexCount"] = vc;

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

// ─── POST /subd/cylinder ────────────────────────────────────────

void HandleSubDCylinder(const httplib::Request& req, httplib::Response& res)
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
    int circumFaces = body.value("circumferenceFaces", 8);
    int heightFaces = body.value("heightFaces", 1);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, center, radius, height, circumFaces, heightFaces]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"SubD cylinder");

        ON_Plane basePlane(center, ON_3dVector::ZAxis);
        ON_Circle circle(basePlane, radius);
        ON_Cylinder cyl(circle, height);

        ON_Brep* brep = ON_BrepCylinder(cyl, true, true);
        if (!brep)
            throw std::invalid_argument("Failed to create cylinder brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        ON_SimpleArray<ON_Mesh*> meshList;
        brep->CreateMesh(mp, meshList);
        if (meshList.Count() == 0)
            throw std::invalid_argument("Failed to mesh cylinder");

        ON_Mesh* mesh = meshList[0];
        for (int i = 1; i < meshList.Count(); ++i)
        {
            if (meshList[i]) { mesh->Append(*meshList[i]); delete meshList[i]; }
        }
        std::unique_ptr<ON_Mesh> meshGuard(mesh);

        ON_SubD* subd = ON_SubD::CreateFromMesh(mesh, nullptr, nullptr);
        if (!subd)
            throw std::invalid_argument("Failed to create SubD from mesh");
        std::unique_ptr<ON_SubD> subdGuard(subd);

        int fc = static_cast<int>(subd->FaceCount());
        int ec = static_cast<int>(subd->EdgeCount());
        int vc = static_cast<int>(subd->VertexCount());

        ON_UUID resultId = AddSubDToDocument(pDoc, *subd);
        if (ON_UuidIsNil(resultId))
            throw std::invalid_argument("Failed to add SubD to document");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["faceCount"] = fc;
        wr.data["edgeCount"] = ec;
        wr.data["vertexCount"] = vc;

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

// ─── POST /subd/from-mesh ───────────────────────────────────────

void HandleSubDFromMesh(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID meshId;
    try { meshId = ParseUuid(body, "meshId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, meshId]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"SubD from mesh");

        const CRhinoObject* obj = pDoc->LookupObject(meshId);
        if (!obj)
            throw std::invalid_argument("Mesh object not found");
        const ON_Mesh* mesh = ON_Mesh::Cast(obj->Geometry());
        if (!mesh)
            throw std::invalid_argument("Object is not a mesh");

        ON_SubD* subd = ON_SubD::CreateFromMesh(mesh, nullptr, nullptr);
        if (!subd)
            throw std::invalid_argument("Failed to create SubD from mesh");
        std::unique_ptr<ON_SubD> subdGuard(subd);

        int fc = static_cast<int>(subd->FaceCount());
        int ec = static_cast<int>(subd->EdgeCount());
        int vc = static_cast<int>(subd->VertexCount());

        ON_UUID resultId = AddSubDToDocument(pDoc, *subd);
        if (ON_UuidIsNil(resultId))
            throw std::invalid_argument("Failed to add SubD to document");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["faceCount"] = fc;
        wr.data["edgeCount"] = ec;
        wr.data["vertexCount"] = vc;

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

// ─── POST /subd/from-surface ────────────────────────────────────

void HandleSubDFromSurface(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID brepId;
    try { brepId = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, brepId]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"SubD from surface");

        const CRhinoObject* obj = pDoc->LookupObject(brepId);
        if (!obj)
            throw std::invalid_argument("Object not found");

        const ON_Geometry* geom = obj->Geometry();
        const ON_Surface* surface = nullptr;
        std::unique_ptr<ON_NurbsSurface> tempSrf;

        // Extract surface from various types
        if (const ON_Surface* srf = ON_Surface::Cast(geom))
        {
            surface = srf;
        }
        else if (const ON_Brep* brep = ON_Brep::Cast(geom))
        {
            if (brep->m_F.Count() == 1)
                surface = brep->m_F[0].SurfaceOf();
        }
        else if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
        {
            tempSrf.reset(ext->NurbsSurface());
            surface = tempSrf.get();
        }

        if (!surface)
            throw std::invalid_argument("Object is not a surface or single-face brep");

        ON_SubDFromSurfaceParameters params = ON_SubDFromSurfaceParameters::ControlNet;
        ON_SubD* subd = ON_SubD::CreateFromSurface(*surface, &params, nullptr);
        if (!subd)
            throw std::invalid_argument("Failed to create SubD from surface");
        std::unique_ptr<ON_SubD> subdGuard(subd);

        int fc = static_cast<int>(subd->FaceCount());
        int ec = static_cast<int>(subd->EdgeCount());
        int vc = static_cast<int>(subd->VertexCount());

        ON_UUID resultId = AddSubDToDocument(pDoc, *subd);
        if (ON_UuidIsNil(resultId))
            throw std::invalid_argument("Failed to add SubD to document");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(resultId);
        wr.data["faceCount"] = fc;
        wr.data["edgeCount"] = ec;
        wr.data["vertexCount"] = vc;

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

// ─── POST /subd/subdivide ───────────────────────────────────────

void HandleSubDSubdivide(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID subdId;
    try { subdId = ParseUuid(body, "subdId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    int level = body.value("level", 1);
    if (level < 1) level = 1;
    if (level > 5) level = 5;

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, subdId, level]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Subdivide SubD");

        const CRhinoObject* obj = pDoc->LookupObject(subdId);
        if (!obj)
            throw std::invalid_argument("SubD object not found");
        const ON_SubD* subd = ON_SubD::Cast(obj->Geometry());
        if (!subd)
            throw std::invalid_argument("Object is not a SubD");

        ON_SubD* newSubD = new ON_SubD(*subd);
        std::unique_ptr<ON_SubD> subdGuard(newSubD);

        for (int i = 0; i < level; ++i)
        {
            if (!newSubD->GlobalSubdivide())
                throw std::invalid_argument("Subdivision failed at level " + std::to_string(i + 1));
        }

        pDoc->ReplaceObject(CRhinoObjRef(obj), *newSubD);

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(subdId);
        wr.data["level"] = level;
        wr.data["faceCount"] = static_cast<int>(newSubD->FaceCount());
        wr.data["vertexCount"] = static_cast<int>(newSubD->VertexCount());

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

// ─── POST /subd/crease ──────────────────────────────────────────

void HandleSubDCrease(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID subdId;
    try { subdId = ParseUuid(body, "subdId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("edgeIndices") || !body["edgeIndices"].is_array())
    {
        CRookServer::SendError(res, "Missing 'edgeIndices' array");
        return;
    }

    std::vector<int> edgeIndices;
    for (const auto& idx : body["edgeIndices"])
    {
        if (idx.is_number_integer())
            edgeIndices.push_back(idx.get<int>());
    }

    bool crease = body.value("crease", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, subdId, edgeIndices = std::move(edgeIndices), crease]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"SubD crease");

        const CRhinoObject* obj = pDoc->LookupObject(subdId);
        if (!obj)
            throw std::invalid_argument("SubD object not found");
        const ON_SubD* subd = ON_SubD::Cast(obj->Geometry());
        if (!subd)
            throw std::invalid_argument("Object is not a SubD");

        ON_SubD* newSubD = new ON_SubD(*subd);
        std::unique_ptr<ON_SubD> subdGuard(newSubD);

        // Build set of target edge indices for fast lookup
        std::set<unsigned int> targetEdges(edgeIndices.begin(), edgeIndices.end());

        int modifiedCount = 0;
        ON_SubDEdgeIterator eit(*newSubD);
        for (const ON_SubDEdge* edge = eit.FirstEdge(); edge != nullptr; edge = eit.NextEdge())
        {
            if (targetEdges.count(edge->m_id) > 0)
            {
                ON_SubDEdge* mutableEdge = const_cast<ON_SubDEdge*>(edge);
                mutableEdge->m_edge_tag = crease
                    ? ON_SubDEdgeTag::Crease
                    : ON_SubDEdgeTag::Smooth;
                modifiedCount++;
            }
        }

        newSubD->UpdateAllTagsAndSectorCoefficients(true);
        pDoc->ReplaceObject(CRhinoObjRef(obj), *newSubD);

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(subdId);
        wr.data["modifiedEdges"] = modifiedCount;
        wr.data["crease"] = crease;

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

// ─── POST /subd/to-brep ─────────────────────────────────────────

void HandleSubDToBrep(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID subdId;
    try { subdId = ParseUuid(body, "subdId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    bool packFaces = body.value("packFaces", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, subdId, packFaces]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"SubD to Brep");

        const CRhinoObject* obj = pDoc->LookupObject(subdId);
        if (!obj)
            throw std::invalid_argument("SubD object not found");
        const ON_SubD* subd = ON_SubD::Cast(obj->Geometry());
        if (!subd)
            throw std::invalid_argument("Object is not a SubD");

        const ON_SubDToBrepParameters& params = packFaces
            ? ON_SubDToBrepParameters::DefaultPacked
            : ON_SubDToBrepParameters::Default;

        ON_Brep* brep = subd->GetSurfaceBrep(params, nullptr);
        if (!brep)
            throw std::invalid_argument("Failed to convert SubD to brep");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        CRhinoBrepObject* newObj = pDoc->AddBrepObject(*brep);
        if (!newObj)
            throw std::invalid_argument("Failed to add brep to document");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(newObj->Attributes().m_uuid);
        wr.data["faceCount"] = brep->m_F.Count();
        wr.data["edgeCount"] = brep->m_E.Count();
        wr.data["vertexCount"] = brep->m_V.Count();

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

// ─── POST /subd/to-mesh ─────────────────────────────────────────

void HandleSubDToMesh(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID subdId;
    try { subdId = ParseUuid(body, "subdId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    int density = body.value("density", 1);
    density = (std::max)(1, (std::min)(5, density));

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, subdId, density]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"SubD to Mesh");

        const CRhinoObject* obj = pDoc->LookupObject(subdId);
        if (!obj)
            throw std::invalid_argument("SubD object not found");
        const ON_SubD* subd = ON_SubD::Cast(obj->Geometry());
        if (!subd)
            throw std::invalid_argument("Object is not a SubD");

        // Convert SubD → Brep → Mesh
        ON_Brep* brep = subd->GetSurfaceBrep(ON_SubDToBrepParameters::Default, nullptr);
        if (!brep)
            throw std::invalid_argument("Failed to convert SubD to brep for meshing");
        std::unique_ptr<ON_Brep> brepGuard(brep);

        ON_MeshParameters mp = ON_MeshParameters::QualityRenderMesh;
        mp.SetMinimumEdgeLength(0.01 / density);
        mp.SetMaximumEdgeLength(1.0 / density);

        ON_SimpleArray<ON_Mesh*> meshList;
        brep->CreateMesh(mp, meshList);
        if (meshList.Count() == 0)
            throw std::invalid_argument("Failed to mesh SubD brep");

        ON_Mesh* mesh = meshList[0];
        for (int i = 1; i < meshList.Count(); ++i)
        {
            if (meshList[i]) { mesh->Append(*meshList[i]); delete meshList[i]; }
        }
        std::unique_ptr<ON_Mesh> meshGuard(mesh);

        CRhinoMeshObject* newObj = pDoc->AddMeshObject(*mesh);
        if (!newObj)
            throw std::invalid_argument("Failed to add mesh to document");

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(newObj->Attributes().m_uuid);
        wr.data["vertexCount"] = mesh->VertexCount();
        wr.data["faceCount"] = mesh->FaceCount();

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
