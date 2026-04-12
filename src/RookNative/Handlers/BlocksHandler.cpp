// BlocksHandler.cpp
//
// Block definition and instance operations (20 unique handlers).
// Covers CRUD, geometry management, instance ops, linked blocks, utilities.

#include "stdafx.h"
#include "Handlers/BlocksHandler.h"
#include "Handlers/GeometryHandler.h"
#include "Infrastructure/LayerHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/PathValidation.h"
#include "Infrastructure/ShapeMetrics.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <set>
#include <algorithm>
#include <cmath>
#include <ctime>
#include <functional>
#include <memory>

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

static int FindDefByName(CRhinoDoc* pDoc, const std::string& name)
{
    ON_wString wName = Utf8ToWide(name);
    return pDoc->m_instance_definition_table.FindInstanceDefinition(wName);
}

static int FindMaterialIndex(CRhinoDoc* pDoc, const std::string& name)
{
    ON_wString wName = Utf8ToWide(name);
    int count = pDoc->m_material_table.MaterialCount();
    for (int i = 0; i < count; ++i)
    {
        const CRhinoMaterial& mat = pDoc->m_material_table[i];
        if (mat.IsDeleted()) continue;
        if (mat.Name().CompareNoCase(wName) == 0)
            return i;
    }
    return -1;
}

static std::string GetLayerFullPath(CRhinoDoc* pDoc, int layerIdx)
{
    ON_wString fullPath;
    pDoc->m_layer_table.GetLayerPathName(layerIdx, fullPath);
    return WideToUtf8(fullPath);
}

static std::vector<ON_UUID> ParseInstanceIds(const nlohmann::json& body)
{
    std::vector<ON_UUID> ids;
    if (body.contains("ids") && body["ids"].is_array())
    {
        for (const auto& el : body["ids"])
        {
            if (!el.is_string()) continue;
            ON_UUID id = ON_UuidFromString(Utf8ToWide(el.get<std::string>()));
            if (!ON_UuidIsNil(id))
                ids.push_back(id);
        }
    }
    else if (body.contains("id") && body["id"].is_string())
    {
        ON_UUID id = ON_UuidFromString(Utf8ToWide(body["id"].get<std::string>()));
        if (!ON_UuidIsNil(id))
            ids.push_back(id);
    }
    return ids;
}

static bool TryParseRgb(const nlohmann::json& value, ON_Color& colorOut)
{
    if (!value.is_array() || value.size() < 3)
        return false;

    int r = std::clamp(value[0].get<int>(), 0, 255);
    int g = std::clamp(value[1].get<int>(), 0, 255);
    int b = std::clamp(value[2].get<int>(), 0, 255);
    colorOut = ON_Color(r, g, b);
    return true;
}

static std::string BlockUserStringKey(const std::string& blockName, const std::string& key)
{
    return "RookBlock::" + blockName + "::" + key;
}

static bool MatchNamePattern(const std::string& value, const std::string& pattern)
{
    if (pattern.empty())
        return true;

    const bool starts = pattern.front() == '*';
    const bool ends = pattern.back() == '*';
    const std::string token = pattern.substr(starts ? 1 : 0, pattern.size() - (starts ? 1 : 0) - (ends ? 1 : 0));

    if (starts && ends)
        return value.find(token) != std::string::npos;
    if (ends)
        return value.rfind(token, 0) == 0;
    if (starts)
    {
        if (value.size() < token.size()) return false;
        return value.compare(value.size() - token.size(), token.size(), token) == 0;
    }
    return _stricmp(value.c_str(), pattern.c_str()) == 0;
}

static std::string GetObjectTypeName(const CRhinoObject* obj)
{
    if (!obj) return "Unknown";
    const ON_Geometry* geom = obj->Geometry();
    if (CRhinoInstanceObject::Cast(obj)) return "InstanceReference";
    if (ON_Brep::Cast(geom)) return "Brep";
    if (ON_Mesh::Cast(geom)) return "Mesh";
    if (ON_Curve::Cast(geom)) return "Curve";
    if (ON_Point::Cast(geom)) return "Point";
    if (ON_Text::Cast(geom)) return "Text";
    return "Other";
}

static nlohmann::json SerializeBlockDef(CRhinoDoc* pDoc,
    const CRhinoInstanceDefinition* pIdef)
{
    if (!pIdef) return nullptr;

    ON_SimpleArray<const CRhinoInstanceObject*> refs;
    pIdef->GetReferences(refs);

    nlohmann::json j;
    j["index"] = pIdef->Index();
    j["id"] = UuidToString(pIdef->Id());
    j["name"] = WideToUtf8(pIdef->Name());
    j["description"] = WideToUtf8(pIdef->Description());
    j["objectCount"] = pIdef->ObjectCount();
    j["instanceCount"] = refs.Count();
    return j;
}

static nlohmann::json BuildNestedHierarchy(CRhinoDoc* pDoc,
    const CRhinoInstanceDefinition* pIdef, std::set<int>& visited)
{
    nlohmann::json result;
    if (!pIdef) return result;

    result["name"] = WideToUtf8(pIdef->Name());
    result["objectCount"] = pIdef->ObjectCount();

    if (visited.count(pIdef->Index()))
    {
        result["circular"] = true;
        result["children"] = nlohmann::json::array();
        return result;
    }

    visited.insert(pIdef->Index());

    nlohmann::json children = nlohmann::json::array();
    for (int i = 0; i < pIdef->ObjectCount(); ++i)
    {
        const CRhinoObject* obj = pIdef->Object(i);
        if (!obj) continue;

        const CRhinoInstanceObject* instObj = CRhinoInstanceObject::Cast(obj);
        if (instObj)
        {
            const CRhinoInstanceDefinition* nestedDef = instObj->InstanceDefinition();
            if (nestedDef)
            {
                std::set<int> childVisited = visited;
                children.push_back(BuildNestedHierarchy(pDoc, nestedDef, childVisited));
            }
        }
    }

    result["children"] = children;
    return result;
}

// Get block name from body (POST) or query params (GET)
static std::string GetBlockName(const httplib::Request& req, const nlohmann::json& body)
{
    if (body.contains("name") && body["name"].is_string())
        return body["name"].get<std::string>();
    if (req.has_param("name"))
        return req.get_param_value("name");
    return "";
}

// Add any geometry type to the document, returns the new object or nullptr
static const CRhinoObject* AddGeometryToDoc(CRhinoDoc* pDoc,
    const ON_Geometry* geom, const ON_3dmObjectAttributes* attrs)
{
    if (const ON_Curve* curve = ON_Curve::Cast(geom))
        return pDoc->AddCurveObject(*curve, attrs);
    if (const ON_Brep* brep = ON_Brep::Cast(geom))
        return pDoc->AddBrepObject(*brep, attrs);
    if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
        return pDoc->AddMeshObject(*mesh, attrs);
    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
    {
        ON_Brep* brep = ext->BrepForm();
        if (brep)
        {
            const CRhinoObject* obj = pDoc->AddBrepObject(*brep, attrs);
            delete brep;
            return obj;
        }
    }
    if (const ON_Point* pt = ON_Point::Cast(geom))
        return pDoc->AddPointObject(pt->point, attrs);
    if (const ON_Surface* srf = ON_Surface::Cast(geom))
    {
        ON_Brep* brep = srf->BrepForm();
        if (brep)
        {
            const CRhinoObject* obj = pDoc->AddBrepObject(*brep, attrs);
            delete brep;
            return obj;
        }
    }
    return nullptr;
}

static nlohmann::json SerializeAttributeUserStrings(const ON_3dmObjectAttributes& attrs)
{
    nlohmann::json userStrings = nlohmann::json::object();
    ON_ClassArray<ON_wString> keys;
    attrs.GetUserStringKeys(keys);
    for (int i = 0; i < keys.Count(); ++i)
    {
        ON_wString value;
        if (attrs.GetUserString(keys[i], value))
            userStrings[WideToUtf8(keys[i])] = WideToUtf8(value);
    }
    return userStrings;
}

static bool ModifyBlockDefinitionObjectAttributes(
    CRhinoDoc* pDoc,
    int idefIndex,
    const std::function<void(int, ON_3dmObjectAttributes&)>& mutator)
{
    const CRhinoInstanceDefinition* def = pDoc->m_instance_definition_table[idefIndex];
    if (!def)
        return false;

    ON_SimpleArray<const CRhinoObject*> newObjects;
    std::vector<std::unique_ptr<CRhinoObject>> ownedObjects;
    ownedObjects.reserve(def->ObjectCount());

    for (int i = 0; i < def->ObjectCount(); ++i)
    {
        const CRhinoObject* obj = def->Object(i);
        if (!obj)
            continue;

        std::unique_ptr<CRhinoObject> dup(obj->DuplicateRhinoObject());
        if (!dup)
            return false;

        ON_3dmObjectAttributes attrs = dup->Attributes();
        mutator(i, attrs);
        dup->Attributes() = attrs;

        newObjects.Append(dup.get());
        ownedObjects.push_back(std::move(dup));
    }

    return pDoc->m_instance_definition_table.ModifyInstanceDefinitionGeometry(idefIndex, newObjects, false);
}

struct RebaseAxes
{
    bool x = true;
    bool y = true;
    bool z = true;
};

static RebaseAxes ParseRebaseAxes(const nlohmann::json& body)
{
    RebaseAxes axes;
    if (!body.contains("axes"))
        return axes;

    if (!body["axes"].is_array() || body["axes"].empty())
        throw std::invalid_argument("'axes' must be a non-empty array containing one or more of 'x', 'y', 'z'");

    axes = { false, false, false };
    for (const auto& axisValue : body["axes"])
    {
        if (!axisValue.is_string())
            throw std::invalid_argument("'axes' entries must be strings");

        const std::string axis = axisValue.get<std::string>();
        if (_stricmp(axis.c_str(), "x") == 0)
            axes.x = true;
        else if (_stricmp(axis.c_str(), "y") == 0)
            axes.y = true;
        else if (_stricmp(axis.c_str(), "z") == 0)
            axes.z = true;
        else
            throw std::invalid_argument("Unsupported axis '" + axis + "'. Expected 'x', 'y', or 'z'");
    }

    if (!axes.x && !axes.y && !axes.z)
        throw std::invalid_argument("'axes' must include at least one of 'x', 'y', or 'z'");

    return axes;
}

static nlohmann::json RebaseAxesToJson(const RebaseAxes& axes)
{
    nlohmann::json values = nlohmann::json::array();
    if (axes.x) values.push_back("x");
    if (axes.y) values.push_back("y");
    if (axes.z) values.push_back("z");
    return values;
}

static ON_BoundingBox GetBlockDefinitionBoundingBox(const CRhinoInstanceDefinition* pDef)
{
    ON_BoundingBox bbox = ON_BoundingBox::EmptyBoundingBox;
    if (!pDef)
        return bbox;

    for (int i = 0; i < pDef->ObjectCount(); ++i)
    {
        const CRhinoObject* obj = pDef->Object(i);
        if (!obj || !obj->Geometry())
            continue;

        // Use CRhinoObject::GetTightBoundingBox for representation-independent bounds.
        // BoundingBox() returns the control-polygon hull for NURBS Breps, which can
        // change when geometry is deep-copied through AddBrepObject. GetTightBoundingBox
        // computes from the evaluated surface, giving stable results regardless of
        // representation history. Using the object-level (not geometry-level) method
        // ensures nested CRhinoInstanceObjects include their instance transforms.
        ON_BoundingBox objBbox;
        if (obj->GetTightBoundingBox(objBbox) && objBbox.IsValid())
            bbox.Union(objBbox);
        else
        {
            objBbox = obj->BoundingBox();
            if (objBbox.IsValid())
                bbox.Union(objBbox);
        }
    }

    return bbox;
}

static int CountNullDefinitionObjects(const CRhinoInstanceDefinition* pDef)
{
    if (!pDef)
        return 0;

    int nullCount = 0;
    for (int i = 0; i < pDef->ObjectCount(); ++i)
    {
        if (pDef->Object(i) == nullptr)
            ++nullCount;
    }
    return nullCount;
}

static int CountNestedDefinitionUses(CRhinoDoc* pDoc, const CRhinoInstanceDefinition* targetDef)
{
    if (!pDoc || !targetDef)
        return 0;

    int nestedUseCount = 0;
    const CRhinoInstanceDefinitionTable& table = pDoc->m_instance_definition_table;
    for (int i = 0; i < table.InstanceDefinitionCount(); ++i)
    {
        const CRhinoInstanceDefinition* candidateDef = table[i];
        if (!candidateDef || candidateDef->IsDeleted())
            continue;

        for (int objectIndex = 0; objectIndex < candidateDef->ObjectCount(); ++objectIndex)
        {
            const CRhinoObject* obj = candidateDef->Object(objectIndex);
            const CRhinoInstanceObject* nestedInstance = CRhinoInstanceObject::Cast(obj);
            if (!nestedInstance)
                continue;

            const CRhinoInstanceDefinition* nestedDef = nestedInstance->InstanceDefinition();
            if (nestedDef && nestedDef->Index() == targetDef->Index())
                ++nestedUseCount;
        }
    }

    return nestedUseCount;
}

static ON_3dPoint GetRebaseAnchorPoint(const ON_BoundingBox& bbox, const std::string& anchor)
{
    if (_stricmp(anchor.c_str(), "bbox_min") == 0)
        return bbox.Min();
    if (_stricmp(anchor.c_str(), "bbox_center") == 0)
        return bbox.Center();
    if (_stricmp(anchor.c_str(), "bbox_max") == 0)
        return bbox.Max();

    throw std::invalid_argument(
        "Unsupported anchor '" + anchor + "'. Expected 'bbox_min', 'bbox_center', or 'bbox_max'");
}

static nlohmann::json Point3dToJsonRounded(const ON_3dPoint& point)
{
    return { RoundTo(point.x, 4), RoundTo(point.y, 4), RoundTo(point.z, 4) };
}

static nlohmann::json Vector3dToJsonRounded(const ON_3dVector& vector)
{
    return { RoundTo(vector.x, 4), RoundTo(vector.y, 4), RoundTo(vector.z, 4) };
}

static nlohmann::json BoundingBoxToJsonRounded(const ON_BoundingBox& bbox)
{
    const ON_3dVector size = bbox.Max() - bbox.Min();
    return {
        {"min", Point3dToJsonRounded(bbox.Min())},
        {"max", Point3dToJsonRounded(bbox.Max())},
        {"size", Vector3dToJsonRounded(size)}
    };
}

static ON_BoundingBox TranslateBoundingBox(const ON_BoundingBox& bbox, const ON_3dVector& delta)
{
    ON_BoundingBox moved = bbox;
    moved.m_min += delta;
    moved.m_max += delta;
    return moved;
}

// Check whether AddGeometryToDoc can handle a given geometry type.
static bool CanMaterializeGeometry(const ON_Geometry* geom)
{
    if (!geom) return false;
    if (ON_Curve::Cast(geom))     return true;
    if (ON_Brep::Cast(geom))      return true;
    if (ON_Mesh::Cast(geom))      return true;
    if (ON_Extrusion::Cast(geom)) return true;
    if (ON_Point::Cast(geom))     return true;
    if (ON_Surface::Cast(geom))   return true;
    return false;
}

static std::string GeometryTypeName(const ON_Geometry* geom)
{
    if (!geom)                     return "null";
    if (ON_Curve::Cast(geom))     return "Curve";
    if (ON_Brep::Cast(geom))      return "Brep";
    if (ON_Mesh::Cast(geom))      return "Mesh";
    if (ON_Extrusion::Cast(geom)) return "Extrusion";
    if (ON_Point::Cast(geom))     return "Point";
    if (ON_Surface::Cast(geom))   return "Surface";
    if (ON_SubD::Cast(geom))      return "SubD";
    return "Unknown";
}

// Check that all objects in a definition can be materialized into the document.
// Returns empty string on success, or a description of unsupported types on failure.
static std::string CheckDefinitionMaterializability(const CRhinoInstanceDefinition* pDef)
{
    if (!pDef) return "null definition";

    std::set<std::string> unsupported;
    for (int i = 0; i < pDef->ObjectCount(); ++i)
    {
        const CRhinoObject* obj = pDef->Object(i);
        if (!obj || !obj->Geometry())
        {
            unsupported.insert("null");
            continue;
        }
        if (!CanMaterializeGeometry(obj->Geometry()))
            unsupported.insert(GeometryTypeName(obj->Geometry()));
    }

    if (unsupported.empty())
        return "";

    std::string msg = "Definition contains geometry types that cannot be rebased: ";
    bool first = true;
    for (const auto& t : unsupported)
    {
        if (!first) msg += ", ";
        msg += t;
        first = false;
    }
    return msg;
}

// Duplicate definition objects, transform them, and materialize into the document
// as temporary objects. Returns document-resident pointers suitable for
// ModifyInstanceDefinitionGeometry. Caller must soft-delete the tempIds afterward.
//
// This avoids the dangling-pointer crash that occurs when unique_ptr-owned duplicates
// are passed to ModifyInstanceDefinitionGeometry and then freed at scope exit.
static bool MaterializeTransformedBlockObjects(
    CRhinoDoc* pDoc,
    const CRhinoInstanceDefinition* pDef,
    const ON_Xform& xform,
    ON_SimpleArray<const CRhinoObject*>& docObjects,
    std::vector<ON_UUID>& tempIds)
{
    if (!pDoc || !pDef)
        return false;

    for (int i = 0; i < pDef->ObjectCount(); ++i)
    {
        const CRhinoObject* obj = pDef->Object(i);
        if (!obj)
            return false;

        const ON_Geometry* srcGeom = obj->Geometry();
        if (!srcGeom)
            return false;

        ON_Geometry* dupGeom = srcGeom->Duplicate();
        if (!dupGeom)
            return false;

        if (!dupGeom->Transform(xform))
        {
            delete dupGeom;
            return false;
        }

        ON_3dmObjectAttributes attrs = obj->Attributes();
        const CRhinoObject* docObj = AddGeometryToDoc(pDoc, dupGeom, &attrs);
        delete dupGeom;

        if (!docObj)
            return false;

        docObjects.Append(docObj);
        tempIds.push_back(docObj->Attributes().m_uuid);
    }

    return docObjects.Count() > 0;
}

// Materialize all objects from a block definition into the document as temporaries.
//
// Two modes controlled by parameters:
//
// LEAF MODE (geometryXform != identity, targetDefIndex < 0):
//   Plain geometry: duplicate, apply geometryXform, AddGeometryToDoc.
//   InstanceRefs: CreateInstanceObject with geometryXform * oldRefXform.
//   Used when rebasing the leaf definition itself.
//
// PARENT MODE (geometryXform == identity, targetDefIndex >= 0):
//   Plain geometry: duplicate unchanged, AddGeometryToDoc.
//   InstanceRefs pointing at targetDefIndex: apply refCompensationXform.
//   Other InstanceRefs: keep original transform.
//   Used when rewriting a parent definition to compensate for a child rebase.
//
// Returns false on any failure; caller must clean up tempIds on failure.
static bool MaterializeDefinitionObjects(
    CRhinoDoc* pDoc,
    const CRhinoInstanceDefinition* pDef,
    const ON_Xform& geometryXform,
    int targetDefIndex,
    const ON_Xform& refCompensationXform,
    ON_SimpleArray<const CRhinoObject*>& docObjects,
    std::vector<ON_UUID>& tempIds)
{
    if (!pDoc || !pDef)
        return false;

    const bool isIdentityGeomXform = geometryXform.IsIdentity(1e-12);

    for (int i = 0; i < pDef->ObjectCount(); ++i)
    {
        const CRhinoObject* obj = pDef->Object(i);
        if (!obj)
            return false;

        const CRhinoInstanceObject* instObj = CRhinoInstanceObject::Cast(obj);
        if (instObj)
        {
            // Nested instance ref — recreate as a document-level instance
            const CRhinoInstanceDefinition* referencedDef = instObj->InstanceDefinition();
            if (!referencedDef)
                return false;

            ON_Xform xform = instObj->InstanceXform();

            if (!isIdentityGeomXform)
            {
                // Leaf mode: post-multiply because the transform lives in the
                // definition's local coordinates, matching the established pattern
                // in HandleBlockRebase (line ~3392). Pre-multiply would be wrong
                // for any ref that includes rotation or scale.
                xform = xform * geometryXform;
            }
            else if (targetDefIndex >= 0 && referencedDef->Index() == targetDefIndex)
            {
                // Parent mode: compensate only refs pointing at the rebased child
                xform = xform * refCompensationXform;
            }

            ON_3dmObjectAttributes attrs = instObj->Attributes();
            CRhinoInstanceObject* pTempInst =
                pDoc->m_instance_definition_table.CreateInstanceObject(
                    referencedDef->Index(), xform, &attrs, nullptr, false, false, true);

            if (!pTempInst)
                return false;

            docObjects.Append(pTempInst);
            tempIds.push_back(pTempInst->Attributes().m_uuid);
        }
        else
        {
            // Plain geometry — duplicate, optionally transform, add to document
            const ON_Geometry* srcGeom = obj->Geometry();
            if (!srcGeom)
                return false;

            ON_Geometry* dupGeom = srcGeom->Duplicate();
            if (!dupGeom)
                return false;

            if (!isIdentityGeomXform)
            {
                if (!dupGeom->Transform(geometryXform))
                {
                    delete dupGeom;
                    return false;
                }
            }

            ON_3dmObjectAttributes attrs = obj->Attributes();
            const CRhinoObject* docObj = AddGeometryToDoc(pDoc, dupGeom, &attrs);
            delete dupGeom;

            if (!docObj)
                return false;

            docObjects.Append(docObj);
            tempIds.push_back(docObj->Attributes().m_uuid);
        }
    }

    return docObjects.Count() > 0;
}

// ─── Core Operations ────────────────────────────────────────────────

// GET /blocks
void HandleGetBlocks(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoInstanceDefinitionTable& table = pDoc->m_instance_definition_table;
        nlohmann::json blocks = nlohmann::json::array();

        for (int i = 0; i < table.InstanceDefinitionCount(); ++i)
        {
            const CRhinoInstanceDefinition* pIdef = table[i];
            if (!pIdef || pIdef->IsDeleted()) continue;
            blocks.push_back(SerializeBlockDef(pDoc, pIdef));
        }

        WriteResult wr;
        wr.success = true;
        wr.data["count"] = static_cast<int>(blocks.size());
        wr.data["blocks"] = std::move(blocks);
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
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/create
void HandleBlockCreate(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> objectIds;
    try { objectIds = ParseUuids(body, "ids"); }
    catch (...) { }
    if (objectIds.empty()) { CRookServer::SendError(res, "No valid object IDs provided"); return; }

    std::string name = body.value("name", "");
    if (name.empty())
    {
        auto t = std::time(nullptr);
        struct tm tm_buf = {};
        localtime_s(&tm_buf, &t);
        char buf[32];
        std::strftime(buf, sizeof(buf), "Block_%Y%m%d%H%M%S", &tm_buf);
        name = buf;
    }

    ON_3dPoint basePoint = ParsePoint3dOrDefault(body, "basePoint", ON_3dPoint::Origin);
    bool deleteObjects = body.value("deleteObjects", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, objectIds, name, basePoint, deleteObjects]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Create block");

        if (FindDefByName(pDoc, name) >= 0)
            throw std::invalid_argument("Block definition '" + name + "' already exists");

        // Collect source objects
        ON_SimpleArray<const CRhinoObject*> srcObjects;
        for (const auto& id : objectIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(id);
            if (obj && obj->Geometry())
                srcObjects.Append(obj);
        }

        if (srcObjects.Count() == 0)
            throw std::invalid_argument("No valid objects found");

        // Set up instance definition settings
        ON_InstanceDefinition idef_settings;
        idef_settings.SetName(Utf8ToWide(name));
        idef_settings.SetDescription(L"");

        int idefIndex = pDoc->m_instance_definition_table.AddInstanceDefinition(
            idef_settings, srcObjects, false, false);

        if (idefIndex < 0)
            throw std::runtime_error("Failed to create block definition");

        WriteResult wr;
        wr.success = true;
        wr.data["definitionIndex"] = idefIndex;
        wr.data["name"] = name;
        wr.data["objectCount"] = srcObjects.Count();
        wr.data["basePoint"] = { basePoint.x, basePoint.y, basePoint.z };

        if (deleteObjects)
        {
            for (const auto& id : objectIds)
            {
                const CRhinoObject* obj = pDoc->LookupObject(id);
                if (obj) pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), id));
            }

            // Insert instance at identity — geometry is already at world coords
            // (C++ SDK has no SetBasePoint; block origin is at world origin)
            ON_Xform xform = ON_Xform::IdentityTransformation;
            CRhinoInstanceObject* pInstObj =
                pDoc->m_instance_definition_table.CreateInstanceObject(
                    idefIndex, xform, nullptr, nullptr, false, false, true);
            if (pInstObj)
                wr.data["instanceId"] = UuidToString(pInstObj->Attributes().m_uuid);
        }

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/insert
void HandleBlockInsert(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = body.value("name", "");
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    ON_3dPoint insertPoint = ParsePoint3dOrDefault(body, "point", ON_3dPoint::Origin);
    double scale = body.value("scale", 1.0);
    if (scale == 0.0 || !std::isfinite(scale))
    { CRookServer::SendError(res, "scale must be a finite non-zero value"); return; }
    double rotation = body.value("rotation", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, insertPoint, scale, rotation]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Insert block");

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        // Build composite transform: Translation * Rotation * Scale
        ON_Xform xform = ON_Xform::IdentityTransformation;

        if (std::abs(scale - 1.0) > 0.0001)
        {
            ON_Xform xScale;
            xScale = ON_Xform::ScaleTransformation(ON_3dPoint::Origin, scale);
            xform = xScale;
        }

        if (std::abs(rotation) > 0.0001)
        {
            ON_Xform xRot;
            xRot.Rotation(rotation * ON_PI / 180.0, ON_3dVector::ZAxis, ON_3dPoint::Origin);
            xform = xRot * xform;
        }

        ON_Xform xTrans = ON_Xform::TranslationTransformation(
            ON_3dVector(insertPoint.x, insertPoint.y, insertPoint.z));
        xform = xTrans * xform;

        CRhinoInstanceObject* pInstObj =
            pDoc->m_instance_definition_table.CreateInstanceObject(
                idefIndex, xform, nullptr, nullptr, false, false, true);

        if (!pInstObj)
            throw std::runtime_error("Failed to insert block instance");

        WriteResult wr;
        wr.success = true;
        wr.data["instanceId"] = UuidToString(pInstObj->Attributes().m_uuid);
        wr.data["blockName"] = name;
        wr.data["point"] = { insertPoint.x, insertPoint.y, insertPoint.z };
        wr.data["scale"] = scale;
        wr.data["rotation"] = rotation;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/explode
void HandleBlockExplode(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID instanceId;
    try { instanceId = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex) { CRookServer::SendError(res, ex.what()); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, instanceId]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Explode block");

        const CRhinoObject* obj = pDoc->LookupObject(instanceId);
        if (!obj) throw std::invalid_argument("Object not found");

        const CRhinoInstanceObject* pInstObj = CRhinoInstanceObject::Cast(obj);
        if (!pInstObj) throw std::invalid_argument("Object is not a block instance");

        const CRhinoInstanceDefinition* pDef = pInstObj->InstanceDefinition();
        if (!pDef) throw std::runtime_error("Could not resolve instance definition");

        ON_Xform instXform = pInstObj->InstanceXform();
        nlohmann::json createdIds = nlohmann::json::array();

        for (int i = 0; i < pDef->ObjectCount(); ++i)
        {
            const CRhinoObject* defObj = pDef->Object(i);
            if (!defObj || !defObj->Geometry()) continue;

            ON_Geometry* dupGeom = defObj->Geometry()->Duplicate();
            if (!dupGeom) continue;

            dupGeom->Transform(instXform);

            ON_3dmObjectAttributes attrs = defObj->Attributes();
            const CRhinoObject* newObj = AddGeometryToDoc(pDoc, dupGeom, &attrs);
            delete dupGeom;

            if (newObj)
                createdIds.push_back(UuidToString(newObj->Attributes().m_uuid));
        }

        pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), instanceId));

        WriteResult wr;
        wr.success = true;
        wr.data["explodedInstanceId"] = UuidToString(instanceId);
        wr.data["createdCount"] = static_cast<int>(createdIds.size());
        wr.data["createdIds"] = std::move(createdIds);

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// DELETE /block
void HandleBlockDelete(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = GetBlockName(req, body);
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }
    bool deleteInstances = body.value("deleteInstances", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, deleteInstances]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Delete block");

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        ON_SimpleArray<const CRhinoInstanceObject*> refs;
        if (pIdef) pIdef->GetReferences(refs);
        int instanceCount = refs.Count();

        bool deleted = pDoc->m_instance_definition_table.DeleteInstanceDefinition(
            idefIndex, deleteInstances, true);

        if (!deleted)
            throw std::runtime_error("Failed to delete block definition '" + name + "'");

        WriteResult wr;
        wr.success = true;
        wr.data["deletedBlock"] = name;
        wr.data["instancesDeleted"] = deleteInstances ? instanceCount : 0;
        wr.data["instancesExisted"] = instanceCount;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// ─── Modification ───────────────────────────────────────────────────

// POST /block/rename
void HandleBlockRename(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string oldName = body.value("name", "");
    std::string newName = body.value("newName", "");
    if (oldName.empty()) { CRookServer::SendError(res, "Block name required"); return; }
    if (newName.empty()) { CRookServer::SendError(res, "New name required"); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, oldName, newName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Rename block");

        int idefIndex = FindDefByName(pDoc, oldName);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + oldName + "' not found");

        int existingIdx = FindDefByName(pDoc, newName);
        if (existingIdx >= 0 && existingIdx != idefIndex)
            throw std::invalid_argument("Block definition '" + newName + "' already exists");

        ON_InstanceDefinition idef_settings;
        idef_settings.SetName(Utf8ToWide(newName));

        bool ok = pDoc->m_instance_definition_table.ModifyInstanceDefinition(
            idef_settings, idefIndex,
            ON_InstanceDefinition::idef_name_setting, true);

        if (!ok)
            throw std::runtime_error("Failed to rename block '" + oldName + "'");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        ON_SimpleArray<const CRhinoInstanceObject*> refs;
        if (pIdef) pIdef->GetReferences(refs);

        WriteResult wr;
        wr.success = true;
        wr.data["oldName"] = oldName;
        wr.data["newName"] = newName;
        wr.data["instanceCount"] = refs.Count();

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/description
void HandleBlockDescription(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = body.value("name", "");
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Set block description");

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        if (!pIdef) throw std::runtime_error("Block definition lookup failed");

        ON_InstanceDefinition idef_settings(*pIdef);
        unsigned int mask = 0;

        if (body.contains("description") && body["description"].is_string())
        {
            idef_settings.SetDescription(Utf8ToWide(body["description"].get<std::string>()));
            mask |= ON_InstanceDefinition::idef_description_setting;
        }
        if (body.contains("url") && body["url"].is_string())
        {
            idef_settings.SetURL(Utf8ToWide(body["url"].get<std::string>()));
            mask |= ON_InstanceDefinition::idef_url_setting;
        }
        if (body.contains("urlDescription") && body["urlDescription"].is_string())
        {
            idef_settings.SetURL_Tag(Utf8ToWide(body["urlDescription"].get<std::string>()));
            mask |= ON_InstanceDefinition::idef_url_setting;
        }

        if (mask == 0)
            mask = ON_InstanceDefinition::idef_description_setting | ON_InstanceDefinition::idef_url_setting;

        bool ok = pDoc->m_instance_definition_table.ModifyInstanceDefinition(
            idef_settings, idefIndex, mask, true);

        if (!ok)
            throw std::runtime_error("Failed to modify block '" + name + "'");

        // Re-read updated values
        const CRhinoInstanceDefinition* pUpdated = pDoc->m_instance_definition_table[idefIndex];

        WriteResult wr;
        wr.success = true;
        wr.data["name"] = name;
        wr.data["description"] = pUpdated ? WideToUtf8(pUpdated->Description()) : "";
        wr.data["url"] = pUpdated ? WideToUtf8(pUpdated->URL()) : "";
        wr.data["urlDescription"] = pUpdated ? WideToUtf8(pUpdated->URL_Tag()) : "";

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// GET+POST /block/info
void HandleBlockInfo(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = GetBlockName(req, body);
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        if (!pIdef) throw std::runtime_error("Block lookup failed");

        ON_SimpleArray<const CRhinoInstanceObject*> refs;
        pIdef->GetReferences(refs);

        // Constituent object info
        nlohmann::json objectInfos = nlohmann::json::array();
        for (int i = 0; i < pIdef->ObjectCount(); ++i)
        {
            const CRhinoObject* obj = pIdef->Object(i);
            if (!obj) continue;

            nlohmann::json oi;
            oi["id"] = UuidToString(obj->Attributes().m_uuid);

            // Object type as string
            ON::object_type ot = obj->ObjectType();
            if (ot == ON::curve_object) oi["type"] = "Curve";
            else if (ot == ON::brep_object) oi["type"] = "Brep";
            else if (ot == ON::mesh_object) oi["type"] = "Mesh";
            else if (ot == ON::surface_object) oi["type"] = "Surface";
            else if (ot == ON::point_object) oi["type"] = "Point";
            else if (ot == ON::extrusion_object) oi["type"] = "Extrusion";
            else if (ot == ON::instance_reference) oi["type"] = "InstanceReference";
            else oi["type"] = "Other";

            oi["layer"] = GetLayerFullPath(pDoc, obj->Attributes().m_layer_index);
            objectInfos.push_back(oi);
        }

        // Block type
        std::string blockType = "Embedded";
        ON_InstanceDefinition::IDEF_UPDATE_TYPE updateType = pIdef->InstanceDefinitionType();
        if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked)
            blockType = "Linked";
        else if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
            blockType = "EmbeddedAndLinked";

        WriteResult wr;
        wr.success = true;
        wr.data["index"] = pIdef->Index();
        wr.data["id"] = UuidToString(pIdef->Id());
        wr.data["name"] = WideToUtf8(pIdef->Name());
        wr.data["description"] = WideToUtf8(pIdef->Description());
        wr.data["url"] = WideToUtf8(pIdef->URL());
        wr.data["urlDescription"] = WideToUtf8(pIdef->URL_Tag());
        wr.data["blockType"] = blockType;
        wr.data["sourceArchive"] = WideToUtf8(pIdef->LinkedFilePath());
        wr.data["objectCount"] = pIdef->ObjectCount();
        wr.data["instanceCount"] = refs.Count();
        wr.data["objects"] = std::move(objectInfos);

        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// ─── Geometry Management ────────────────────────────────────────────

// POST /block/add-objects
void HandleBlockAddObjects(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = body.value("name", "");
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    std::vector<ON_UUID> objectIds;
    try { objectIds = ParseUuids(body, "ids"); }
    catch (...) { }
    if (objectIds.empty()) { CRookServer::SendError(res, "No valid object IDs provided"); return; }

    bool deleteOriginals = body.value("deleteOriginals", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, objectIds, deleteOriginals]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Add objects to block");

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        if (!pIdef) throw std::runtime_error("Block lookup failed");

        // Collect existing + new objects
        ON_SimpleArray<const CRhinoObject*> allObjects;

        for (int i = 0; i < pIdef->ObjectCount(); ++i)
        {
            const CRhinoObject* obj = pIdef->Object(i);
            if (obj) allObjects.Append(obj);
        }

        int addedCount = 0;
        for (const auto& id : objectIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(id);
            if (obj && obj->Geometry())
            {
                allObjects.Append(obj);
                ++addedCount;
            }
        }

        if (addedCount == 0)
            throw std::invalid_argument("No valid objects found to add");

        bool ok = pDoc->m_instance_definition_table.ModifyInstanceDefinitionGeometry(
            idefIndex, allObjects, false);

        if (!ok)
            throw std::runtime_error("Failed to add objects to block '" + name + "'");

        if (deleteOriginals)
        {
            for (const auto& id : objectIds)
                pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), id));
        }

        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = name;
        wr.data["addedCount"] = addedCount;
        wr.data["newObjectCount"] = allObjects.Count();
        wr.data["originalsDeleted"] = deleteOriginals;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/remove-objects
void HandleBlockRemoveObjects(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = body.value("name", "");
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    if (!body.contains("indices") || !body["indices"].is_array())
    { CRookServer::SendError(res, "No indices provided"); return; }

    std::set<int> indicesToRemove;
    for (const auto& idx : body["indices"])
    {
        if (!idx.is_number_integer())
        { CRookServer::SendError(res, "indices must be integers"); return; }
        indicesToRemove.insert(idx.get<int>());
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, indicesToRemove]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Remove objects from block");

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        if (!pIdef) throw std::runtime_error("Block lookup failed");

        int objCount = pIdef->ObjectCount();

        for (int idx : indicesToRemove)
        {
            if (idx < 0 || idx >= objCount)
                throw std::invalid_argument("Invalid index: " + std::to_string(idx) +
                    ". Block has " + std::to_string(objCount) + " objects.");
        }

        if (static_cast<int>(indicesToRemove.size()) >= objCount)
            throw std::invalid_argument("Cannot remove all objects. At least one must remain.");

        ON_SimpleArray<const CRhinoObject*> remaining;
        for (int i = 0; i < objCount; ++i)
        {
            if (indicesToRemove.count(i)) continue;
            const CRhinoObject* obj = pIdef->Object(i);
            if (obj) remaining.Append(obj);
        }

        bool ok = pDoc->m_instance_definition_table.ModifyInstanceDefinitionGeometry(
            idefIndex, remaining, false);

        if (!ok)
            throw std::runtime_error("Failed to remove objects from block '" + name + "'");

        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = name;
        wr.data["removedCount"] = static_cast<int>(indicesToRemove.size());
        wr.data["remainingCount"] = remaining.Count();

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/replace-geometry
void HandleBlockReplaceGeometry(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = body.value("name", "");
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    std::vector<ON_UUID> objectIds;
    try { objectIds = ParseUuids(body, "ids"); }
    catch (...) { }
    if (objectIds.empty()) { CRookServer::SendError(res, "No valid object IDs provided"); return; }
    bool deleteOriginals = body.value("deleteOriginals", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, objectIds, deleteOriginals]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Replace block geometry");

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        int oldCount = pIdef ? pIdef->ObjectCount() : 0;

        ON_SimpleArray<const CRhinoObject*> newObjects;
        for (const auto& id : objectIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(id);
            if (obj && obj->Geometry())
                newObjects.Append(obj);
        }

        if (newObjects.Count() == 0)
            throw std::invalid_argument("No valid objects found for replacement");

        bool ok = pDoc->m_instance_definition_table.ModifyInstanceDefinitionGeometry(
            idefIndex, newObjects, false);

        if (!ok)
            throw std::runtime_error("Failed to replace geometry in block '" + name + "'");

        if (deleteOriginals)
        {
            for (const auto& id : objectIds)
                pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), id));
        }

        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = name;
        wr.data["previousObjectCount"] = oldCount;
        wr.data["newObjectCount"] = newObjects.Count();
        wr.data["originalsDeleted"] = deleteOriginals;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// ─── Instance Operations ────────────────────────────────────────────

// GET+POST /block/instances
void HandleBlockInstances(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = GetBlockName(req, body);
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    int depth = body.value("depth", 0);
    if (req.has_param("depth"))
    {
        try { depth = std::stoi(req.get_param_value("depth")); }
        catch (...) { /* ignore invalid, use body/default */ }
    }
    if (depth < 0) depth = 0;

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, depth]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        if (!pIdef) throw std::runtime_error("Block lookup failed");

        ON_SimpleArray<const CRhinoInstanceObject*> refs;
        pIdef->GetReferences(refs, depth);

        nlohmann::json instances = nlohmann::json::array();
        for (int i = 0; i < refs.Count(); ++i)
        {
            const CRhinoInstanceObject* inst = refs[i];
            if (!inst) continue;

            ON_Xform xf = inst->InstanceXform();

            nlohmann::json insertPt = { xf[0][3], xf[1][3], xf[2][3] };

            double sx = std::sqrt(xf[0][0]*xf[0][0] + xf[1][0]*xf[1][0] + xf[2][0]*xf[2][0]);
            double sy = std::sqrt(xf[0][1]*xf[0][1] + xf[1][1]*xf[1][1] + xf[2][1]*xf[2][1]);
            double sz = std::sqrt(xf[0][2]*xf[0][2] + xf[1][2]*xf[1][2] + xf[2][2]*xf[2][2]);

            nlohmann::json ji;
            ji["id"] = UuidToString(inst->Attributes().m_uuid);
            ji["insertionPoint"] = insertPt;
            ji["scale"] = { sx, sy, sz };
            ji["layer"] = GetLayerFullPath(pDoc, inst->Attributes().m_layer_index);
            ji["name"] = WideToUtf8(inst->Attributes().m_name);

            instances.push_back(ji);
        }

        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = name;
        wr.data["depth"] = depth;
        wr.data["instanceCount"] = static_cast<int>(instances.size());
        wr.data["instances"] = std::move(instances);

        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/replace-instance
void HandleBlockReplaceInstance(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID instanceId;
    try { instanceId = ParseUuid(body, "instanceId"); }
    catch (const std::invalid_argument& ex) { CRookServer::SendError(res, ex.what()); return; }

    std::string newBlockName = body.value("newBlockName", "");
    if (newBlockName.empty()) { CRookServer::SendError(res, "New block name required"); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, instanceId, newBlockName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Replace block instance");

        const CRhinoObject* obj = pDoc->LookupObject(instanceId);
        if (!obj) throw std::invalid_argument("Object not found");

        const CRhinoInstanceObject* pInstObj = CRhinoInstanceObject::Cast(obj);
        if (!pInstObj) throw std::invalid_argument("Object is not a block instance");

        int newDefIndex = FindDefByName(pDoc, newBlockName);
        if (newDefIndex < 0)
            throw std::invalid_argument("Block definition '" + newBlockName + "' not found");

        const CRhinoInstanceDefinition* pOldDef = pInstObj->InstanceDefinition();
        if (!pOldDef) throw std::runtime_error("Could not resolve instance definition");
        std::string oldBlockName = WideToUtf8(pOldDef->Name());
        ON_Xform oldXform = pInstObj->InstanceXform();
        ON_3dmObjectAttributes oldAttrs = pInstObj->Attributes();

        // Delete old instance, create new with same transform
        pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), instanceId));

        CRhinoInstanceObject* pNewInst =
            pDoc->m_instance_definition_table.CreateInstanceObject(
                newDefIndex, oldXform, &oldAttrs, nullptr, false, false, true);

        if (!pNewInst)
            throw std::runtime_error("Failed to replace block instance");

        WriteResult wr;
        wr.success = true;
        wr.data["instanceId"] = UuidToString(pNewInst->Attributes().m_uuid);
        wr.data["oldBlockName"] = oldBlockName;
        wr.data["newBlockName"] = newBlockName;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/reset-scale
void HandleBlockResetScale(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID instanceId;
    try { instanceId = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex) { CRookServer::SendError(res, ex.what()); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, instanceId]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Reset block scale");

        const CRhinoObject* obj = pDoc->LookupObject(instanceId);
        if (!obj) throw std::invalid_argument("Object not found");

        const CRhinoInstanceObject* pInstObj = CRhinoInstanceObject::Cast(obj);
        if (!pInstObj) throw std::invalid_argument("Object is not a block instance");

        ON_Xform oldXform = pInstObj->InstanceXform();
        const CRhinoInstanceDefinition* pDef = pInstObj->InstanceDefinition();
        if (!pDef) throw std::runtime_error("Could not resolve instance definition");
        int idefIndex = pDef->Index();
        ON_3dmObjectAttributes attrs = pInstObj->Attributes();

        ON_3dVector translation(oldXform[0][3], oldXform[1][3], oldXform[2][3]);
        ON_Xform newXform = ON_Xform::TranslationTransformation(translation);

        pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), instanceId));

        CRhinoInstanceObject* pNewInst =
            pDoc->m_instance_definition_table.CreateInstanceObject(
                idefIndex, newXform, &attrs, nullptr, false, false, true);

        if (!pNewInst)
            throw std::runtime_error("Failed to reset block scale");

        WriteResult wr;
        wr.success = true;
        wr.data["oldInstanceId"] = UuidToString(instanceId);
        wr.data["newInstanceId"] = UuidToString(pNewInst->Attributes().m_uuid);
        wr.data["scale"] = { 1.0, 1.0, 1.0 };

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/set-instance-properties
void HandleBlockSetInstanceProperties(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    if (body.is_null() || body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }

    std::vector<ON_UUID> instanceIds = ParseInstanceIds(body);
    if (instanceIds.empty())
    {
        CRookServer::SendError(res, "At least one instance ID required ('id' or 'ids')");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, instanceIds]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Set Instance Properties");

        int layerIndex = -1;
        if (body.contains("layer") && body["layer"].is_string())
        {
            const auto layerRef = Rook::Infrastructure::ResolveLayerRef(
                pDoc, body["layer"].get<std::string>(), "layer");
            layerIndex = layerRef.index;
        }

        int materialIndex = -1;
        if (body.contains("material") && body["material"].is_string())
        {
            materialIndex = FindMaterialIndex(pDoc, body["material"].get<std::string>());
            if (materialIndex < 0)
                throw std::invalid_argument("Material '" + body["material"].get<std::string>() + "' not found");
        }

        ON_Color color = ON_Color::UnsetColor;
        const bool hasColor = body.contains("color") && TryParseRgb(body["color"], color);
        const bool hasName = body.contains("name") && body["name"].is_string();
        const std::string newName = hasName ? body["name"].get<std::string>() : "";

        nlohmann::json results = nlohmann::json::array();
        int modifiedCount = 0;

        for (const auto& id : instanceIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(id);
            const CRhinoInstanceObject* inst = CRhinoInstanceObject::Cast(obj);
            if (!inst)
            {
                nlohmann::json item;
                item["id"] = UuidToString(id);
                item["success"] = false;
                item["error"] = "Not found or not a block instance";
                results.push_back(std::move(item));
                continue;
            }

            ON_3dmObjectAttributes attrs = inst->Attributes();
            if (hasName)
                attrs.m_name = Utf8ToWide(newName);
            if (layerIndex >= 0)
                attrs.m_layer_index = layerIndex;
            if (hasColor)
            {
                attrs.SetColorSource(ON::color_from_object);
                attrs.m_color = color;
            }
            if (materialIndex >= 0)
            {
                attrs.SetMaterialSource(ON::material_from_object);
                attrs.m_material_index = materialIndex;
            }
            if (body.contains("userStrings") && body["userStrings"].is_object())
            {
                for (auto it = body["userStrings"].begin(); it != body["userStrings"].end(); ++it)
                {
                    if (it.value().is_string())
                        attrs.SetUserString(Utf8ToWide(it.key()), Utf8ToWide(it.value().get<std::string>()));
                }
            }

            if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
            {
                nlohmann::json item;
                item["id"] = UuidToString(id);
                item["success"] = false;
                item["error"] = "Failed to modify instance attributes";
                results.push_back(std::move(item));
                continue;
            }

            const CRhinoObject* updated = pDoc->LookupObject(id);
            const ON_3dmObjectAttributes& updatedAttrs = updated ? updated->Attributes() : attrs;

            nlohmann::json item;
            item["id"] = UuidToString(id);
            item["success"] = true;
            item["name"] = WideToUtf8(updatedAttrs.m_name);
            item["layer"] = GetLayerFullPath(pDoc, updatedAttrs.m_layer_index);
            if (updatedAttrs.ColorSource() == ON::color_from_object)
                item["color"] = { updatedAttrs.m_color.Red(), updatedAttrs.m_color.Green(), updatedAttrs.m_color.Blue() };
            if (updatedAttrs.MaterialSource() == ON::material_from_object && updatedAttrs.m_material_index >= 0)
                item["material"] = WideToUtf8(pDoc->m_material_table[updatedAttrs.m_material_index].Name());

            results.push_back(std::move(item));
            modifiedCount++;
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["modifiedCount"] = modifiedCount;
        wr.data["instances"] = std::move(results);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/set-instance-visibility
void HandleBlockSetInstanceVisibility(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    if (body.is_null() || body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }

    std::vector<ON_UUID> instanceIds = ParseInstanceIds(body);
    if (instanceIds.empty())
    {
        CRookServer::SendError(res, "At least one instance ID required");
        return;
    }
    if (!body.contains("visible") || !body["visible"].is_boolean())
    {
        CRookServer::SendError(res, "'visible' parameter required (true/false)");
        return;
    }
    const bool visible = body["visible"].get<bool>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, instanceIds, visible]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Set Instance Visibility");

        int modifiedCount = 0;
        for (const auto& id : instanceIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(id);
            if (!CRhinoInstanceObject::Cast(obj))
                continue;

            const bool ok = visible
                ? pDoc->ShowObject(CRhinoObjRef(obj), true)
                : pDoc->HideObject(CRhinoObjRef(obj), true);
            if (ok)
                modifiedCount++;
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["visible"] = visible;
        wr.data["modifiedCount"] = modifiedCount;
        wr.data["requestedCount"] = static_cast<int>(instanceIds.size());
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/transform-instance
void HandleBlockTransformInstance(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    if (body.is_null() || body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }

    ON_UUID instanceId;
    try { instanceId = ParseUuid(body, "id"); }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, instanceId]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(instanceId);
        const CRhinoInstanceObject* inst = CRhinoInstanceObject::Cast(obj);
        if (!inst)
            throw std::invalid_argument("Object is not a block instance");

        const ON_3dPoint pivot(inst->InstanceXform().m_xform[0][3], inst->InstanceXform().m_xform[1][3], inst->InstanceXform().m_xform[2][3]);
        ON_Xform combined = ON_Xform::IdentityTransformation;
        nlohmann::json ops = nlohmann::json::array();

        if (body.contains("scale"))
        {
            if (body["scale"].is_array() && body["scale"].size() >= 3)
            {
                ON_Xform s = ON_Xform::ScaleTransformation(ON_Plane(pivot, ON_3dVector::XAxis, ON_3dVector::YAxis),
                    body["scale"][0].get<double>(), body["scale"][1].get<double>(), body["scale"][2].get<double>());
                combined = s * combined;
                ops.push_back("scale");
            }
            else if (body["scale"].is_number())
            {
                ON_Xform s = ON_Xform::ScaleTransformation(pivot, body["scale"].get<double>());
                combined = s * combined;
                ops.push_back("scale");
            }
        }

        if (body.contains("rotate") && body["rotate"].is_number())
        {
            ON_Xform r;
            r.Rotation(body["rotate"].get<double>() * ON_PI / 180.0, ON_3dVector::ZAxis, pivot);
            combined = r * combined;
            ops.push_back("rotate");
        }

        if (body.contains("move") && body["move"].is_array() && body["move"].size() >= 3)
        {
            ON_Xform t = ON_Xform::TranslationTransformation(ON_3dVector(
                body["move"][0].get<double>(),
                body["move"][1].get<double>(),
                body["move"][2].get<double>()));
            combined = t * combined;
            ops.push_back("move");
        }

        if (body.contains("mirror") && body["mirror"].is_object())
        {
            ON_3dPoint origin = ON_3dPoint::Origin;
            ON_3dVector normal = ON_3dVector::YAxis;
            const auto& mirror = body["mirror"];
            if (mirror.contains("origin") && mirror["origin"].is_array() && mirror["origin"].size() >= 3)
                origin = ON_3dPoint(mirror["origin"][0].get<double>(), mirror["origin"][1].get<double>(), mirror["origin"][2].get<double>());
            if (mirror.contains("normal") && mirror["normal"].is_array() && mirror["normal"].size() >= 3)
                normal = ON_3dVector(mirror["normal"][0].get<double>(), mirror["normal"][1].get<double>(), mirror["normal"][2].get<double>());
            ON_Plane mirrorPlane(origin, normal);
            ON_Xform m = ON_Xform::MirrorTransformation(mirrorPlane.plane_equation);
            combined = m * combined;
            ops.push_back("mirror");
        }

        if (ops.empty())
            throw std::invalid_argument("At least one transform required: 'move', 'rotate', 'scale', or 'mirror'");

        UndoScope undo(pDoc, L"Transform Block Instance");
        ON_3dmObjectAttributes attrs = inst->Attributes();
        const CRhinoInstanceDefinition* def = inst->InstanceDefinition();
        if (!def)
            throw std::runtime_error("Could not resolve instance definition");

        ON_Xform newXform = combined * inst->InstanceXform();
        pDoc->DeleteObject(CRhinoObjRef(obj));
        CRhinoInstanceObject* newInst = pDoc->m_instance_definition_table.CreateInstanceObject(
            def->Index(), newXform, &attrs, nullptr, false, false, true);
        if (!newInst)
            throw std::runtime_error("Failed to transform block instance");

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(newInst->Attributes().m_uuid);
        wr.data["operations"] = std::move(ops);
        wr.data["newPosition"] = { newXform.m_xform[0][3], newXform.m_xform[1][3], newXform.m_xform[2][3] };
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/array-instances
void HandleBlockArrayInstances(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    if (body.is_null() || body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }
    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Block 'name' required");
        return;
    }
    if (!body.contains("count") || !body["count"].is_number_integer())
    {
        CRookServer::SendError(res, "'count' is required");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const std::string blockName = body["name"].get<std::string>();
        const int idefIndex = FindDefByName(pDoc, blockName);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + blockName + "' not found");

        const int count = body["count"].get<int>();
        if (count < 1)
            throw std::invalid_argument("'count' must be >= 1");

        const double scale = body.value("scale", 1.0);
        const bool isCircular = body.contains("center");
        nlohmann::json createdIds = nlohmann::json::array();

        UndoScope undo(pDoc, L"Array Block Instances");

        if (isCircular)
        {
            ON_3dPoint center = ON_3dPoint::Origin;
            if (body["center"].is_array() && body["center"].size() >= 3)
                center = ON_3dPoint(body["center"][0].get<double>(), body["center"][1].get<double>(), body["center"][2].get<double>());

            const double radius = body.value("radius", 10.0);
            const double startAngle = body.value("startAngle", 0.0);
            const double endAngle = body.value("endAngle", 360.0);
            const double span = endAngle - startAngle;
            const double step = std::abs(span - 360.0) < 0.001 ? span / count : span / (std::max)(count - 1, 1);

            for (int i = 0; i < count; ++i)
            {
                const double angle = startAngle + i * step;
                const double rad = angle * ON_PI / 180.0;
                ON_3dPoint point(center.x + radius * std::cos(rad), center.y + radius * std::sin(rad), center.z);

                ON_Xform xform = ON_Xform::IdentityTransformation;
                if (std::abs(scale - 1.0) > 0.0001)
                    xform = ON_Xform::ScaleTransformation(ON_3dPoint::Origin, scale);
                ON_Xform rot;
                rot.Rotation(rad, ON_3dVector::ZAxis, ON_3dPoint::Origin);
                xform = rot * xform;
                xform = ON_Xform::TranslationTransformation(point - ON_3dPoint::Origin) * xform;

                CRhinoInstanceObject* inst = pDoc->m_instance_definition_table.CreateInstanceObject(idefIndex, xform, nullptr, nullptr, false, false, true);
                if (inst) createdIds.push_back(UuidToString(inst->Attributes().m_uuid));
            }
        }
        else
        {
            if (!body.contains("direction") || !body["direction"].is_array() || body["direction"].size() < 3)
                throw std::invalid_argument("Either 'direction' (linear) or 'center' (circular) required");

            ON_3dVector direction(body["direction"][0].get<double>(), body["direction"][1].get<double>(), body["direction"][2].get<double>());
            ON_3dPoint basePoint = ON_3dPoint::Origin;
            if (body.contains("basePoint") && body["basePoint"].is_array() && body["basePoint"].size() >= 3)
                basePoint = ON_3dPoint(body["basePoint"][0].get<double>(), body["basePoint"][1].get<double>(), body["basePoint"][2].get<double>());

            for (int i = 0; i < count; ++i)
            {
                ON_3dPoint point(basePoint.x + i * direction.x, basePoint.y + i * direction.y, basePoint.z + i * direction.z);
                ON_Xform xform = ON_Xform::IdentityTransformation;
                if (std::abs(scale - 1.0) > 0.0001)
                    xform = ON_Xform::ScaleTransformation(ON_3dPoint::Origin, scale);
                xform = ON_Xform::TranslationTransformation(point - ON_3dPoint::Origin) * xform;

                CRhinoInstanceObject* inst = pDoc->m_instance_definition_table.CreateInstanceObject(idefIndex, xform, nullptr, nullptr, false, false, true);
                if (inst) createdIds.push_back(UuidToString(inst->Attributes().m_uuid));
            }
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = blockName;
        wr.data["mode"] = isCircular ? "circular" : "linear";
        wr.data["createdCount"] = static_cast<int>(createdIds.size());
        wr.data["instanceIds"] = std::move(createdIds);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/find-instances
void HandleBlockFindInstances(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const std::string blockName = body.value("name", "");
        const std::string layerFilter = body.value("layer", "");
        const std::string namePattern = body.value("namePattern", "");
        int filterLayerIdx = -1;
        if (!layerFilter.empty())
        {
            filterLayerIdx = Rook::Infrastructure::ResolveLayerRef(pDoc, layerFilter, "layer").index;
        }

        bool hasBbox = false;
        ON_BoundingBox bboxFilter;
        if (body.contains("bbox") && body["bbox"].is_object()
            && body["bbox"].contains("min") && body["bbox"].contains("max")
            && body["bbox"]["min"].is_array() && body["bbox"]["max"].is_array()
            && body["bbox"]["min"].size() >= 3 && body["bbox"]["max"].size() >= 3)
        {
            bboxFilter = ON_BoundingBox(
                ON_3dPoint(body["bbox"]["min"][0].get<double>(), body["bbox"]["min"][1].get<double>(), body["bbox"]["min"][2].get<double>()),
                ON_3dPoint(body["bbox"]["max"][0].get<double>(), body["bbox"]["max"][1].get<double>(), body["bbox"]["max"][2].get<double>()));
            hasBbox = bboxFilter.IsValid();
        }

        std::vector<const CRhinoInstanceDefinition*> defs;
        if (!blockName.empty())
        {
            int idx = FindDefByName(pDoc, blockName);
            if (idx >= 0)
                defs.push_back(pDoc->m_instance_definition_table[idx]);
        }
        else
        {
            for (int i = 0; i < pDoc->m_instance_definition_table.InstanceDefinitionCount(); ++i)
            {
                const CRhinoInstanceDefinition* def = pDoc->m_instance_definition_table[i];
                if (def && !def->IsDeleted())
                    defs.push_back(def);
            }
        }

        nlohmann::json matches = nlohmann::json::array();
        for (const CRhinoInstanceDefinition* def : defs)
        {
            ON_SimpleArray<const CRhinoInstanceObject*> refs;
            def->GetReferences(refs);
            for (int i = 0; i < refs.Count(); ++i)
            {
                const CRhinoInstanceObject* inst = refs[i];
                if (!inst) continue;

                if (filterLayerIdx >= 0 && inst->Attributes().m_layer_index != filterLayerIdx)
                    continue;

                const std::string instanceName = WideToUtf8(inst->Attributes().m_name);
                if (!namePattern.empty() && !MatchNamePattern(instanceName, namePattern))
                    continue;

                if (hasBbox)
                {
                    ON_BoundingBox instBbox = inst->BoundingBox();
                    if (!instBbox.IsValid()) continue;
                    ON_BoundingBox intersection;
                    if (!intersection.Intersection(instBbox, bboxFilter)) continue;
                }

                const ON_Xform& xf = inst->InstanceXform();
                nlohmann::json item;
                item["id"] = UuidToString(inst->Attributes().m_uuid);
                item["blockName"] = WideToUtf8(def->Name());
                item["insertionPoint"] = { xf.m_xform[0][3], xf.m_xform[1][3], xf.m_xform[2][3] };
                item["layer"] = GetLayerFullPath(pDoc, inst->Attributes().m_layer_index);
                item["name"] = instanceName;
                matches.push_back(std::move(item));
            }
        }

        WriteResult wr;
        wr.success = true;
        wr.data["matchCount"] = static_cast<int>(matches.size());
        wr.data["instances"] = std::move(matches);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// GET+POST /block/user-strings
void HandleBlockUserStrings(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string blockName;
    if (!body.is_null() && body.contains("name") && body["name"].is_string())
        blockName = body["name"].get<std::string>();
    else if (req.has_param("name"))
        blockName = req.get_param_value("name");
    if (blockName.empty())
    {
        CRookServer::SendError(res, "Block name required");
        return;
    }

    std::string action = "get";
    if (!body.is_null() && body.contains("action") && body["action"].is_string())
        action = body["action"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, blockName, action]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const int idefIndex = FindDefByName(pDoc, blockName);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + blockName + "' not found");

        const std::string prefix = "RookBlock::" + blockName + "::";

        if (_stricmp(action.c_str(), "get") == 0)
        {
            ON_ClassArray<ON_wString> keys;
            pDoc->GetUserStringKeys(keys);
            nlohmann::json strings = nlohmann::json::object();
            for (int i = 0; i < keys.Count(); ++i)
            {
                std::string key = WideToUtf8(keys[i]);
                if (key.size() <= prefix.size())
                    continue;
                if (_strnicmp(key.c_str(), prefix.c_str(), prefix.size()) != 0)
                    continue;
                ON_wString value;
                if (pDoc->GetUserString(keys[i], value))
                {
                    strings[key.substr(prefix.size())] = WideToUtf8(value);
                }
            }

            WriteResult wr;
            wr.success = true;
            wr.data["blockName"] = blockName;
            wr.data["userStrings"] = std::move(strings);
            wr.data["count"] = static_cast<int>(wr.data["userStrings"].size());
            return wr;
        }

        UndoScope undo(pDoc, L"Edit Block User Strings");
        if (_stricmp(action.c_str(), "set") == 0)
        {
            if (!body.contains("userStrings") || !body["userStrings"].is_object())
                throw std::invalid_argument("'userStrings' object required for 'set' action");

            int setCount = 0;
            for (auto it = body["userStrings"].begin(); it != body["userStrings"].end(); ++it)
            {
                const std::string key = BlockUserStringKey(blockName, it.key());
                const std::string value = it.value().is_string() ? it.value().get<std::string>() : "";
                pDoc->SetUserString(Utf8ToWide(key), Utf8ToWide(value));
                setCount++;
            }

            WriteResult wr;
            wr.success = true;
            wr.data["blockName"] = blockName;
            wr.data["action"] = "set";
            wr.data["keysSet"] = setCount;
            return wr;
        }

        if (_stricmp(action.c_str(), "delete") == 0)
        {
            if (!body.contains("keys") || !body["keys"].is_array())
                throw std::invalid_argument("'keys' array required for 'delete' action");

            int deletedCount = 0;
            for (const auto& el : body["keys"])
            {
                if (!el.is_string()) continue;
                const std::string key = BlockUserStringKey(blockName, el.get<std::string>());
                if (pDoc->SetUserString(Utf8ToWide(key), nullptr))
                    deletedCount++;
            }

            WriteResult wr;
            wr.success = true;
            wr.data["blockName"] = blockName;
            wr.data["action"] = "delete";
            wr.data["keysDeleted"] = deletedCount;
            return wr;
        }

        throw std::invalid_argument("Unknown action '" + action + "'. Use 'get', 'set', or 'delete'");
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// GET+POST /block/objects-detailed
void HandleBlockObjectsDetailed(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string blockName;
    if (!body.is_null() && body.contains("name") && body["name"].is_string())
        blockName = body["name"].get<std::string>();
    else if (req.has_param("name"))
        blockName = req.get_param_value("name");
    if (blockName.empty())
    {
        CRookServer::SendError(res, "Block name required");
        return;
    }

    bool includeGeometry = false;
    if (!body.is_null() && body.contains("geometry") && body["geometry"].is_boolean())
        includeGeometry = body["geometry"].get<bool>();
    else if (req.has_param("geometry"))
        includeGeometry = (req.get_param_value("geometry") == "true");

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, blockName, includeGeometry]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        int idefIndex = FindDefByName(pDoc, blockName);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + blockName + "' not found");

        const CRhinoInstanceDefinition* def = pDoc->m_instance_definition_table[idefIndex];
        if (!def)
            throw std::runtime_error("Block lookup failed");

        nlohmann::json objects = nlohmann::json::array();
        ON_BoundingBox defBbox = ON_BoundingBox::EmptyBoundingBox;
        for (int i = 0; i < def->ObjectCount(); ++i)
        {
            const CRhinoObject* obj = def->Object(i);
            if (!obj || !obj->Geometry()) continue;

            const ON_3dmObjectAttributes& attrs = obj->Attributes();
            nlohmann::json info;
            info["index"] = i;
            info["id"] = UuidToString(attrs.m_uuid);
            info["type"] = GetObjectTypeName(obj);
            info["name"] = WideToUtf8(attrs.m_name);
            info["layer"] = GetLayerFullPath(pDoc, attrs.m_layer_index);
            info["color"] = { attrs.m_color.Red(), attrs.m_color.Green(), attrs.m_color.Blue() };

            switch (attrs.ColorSource())
            {
            case ON::color_from_object: info["colorSource"] = "ColorFromObject"; break;
            case ON::color_from_parent: info["colorSource"] = "ColorFromParent"; break;
            case ON::color_from_material: info["colorSource"] = "ColorFromMaterial"; break;
            default: info["colorSource"] = "ColorFromLayer"; break;
            }
            switch (attrs.MaterialSource())
            {
            case ON::material_from_object: info["materialSource"] = "MaterialFromObject"; break;
            case ON::material_from_parent: info["materialSource"] = "MaterialFromParent"; break;
            case ON::material_from_layer: info["materialSource"] = "MaterialFromLayer"; break;
            default: info["materialSource"] = "MaterialFromObject"; break;
            }

            info["visible"] = obj->IsVisible();
            if (attrs.MaterialSource() == ON::material_from_object && attrs.m_material_index >= 0 && attrs.m_material_index < pDoc->m_material_table.MaterialCount())
                info["material"] = WideToUtf8(pDoc->m_material_table[attrs.m_material_index].Name());

            ON_ClassArray<ON_wString> keys;
            attrs.GetUserStringKeys(keys);
            if (keys.Count() > 0)
            {
                nlohmann::json userStrings = nlohmann::json::object();
                for (int k = 0; k < keys.Count(); ++k)
                {
                    ON_wString value;
                    if (attrs.GetUserString(keys[k], value))
                        userStrings[WideToUtf8(keys[k])] = WideToUtf8(value);
                }
                if (!userStrings.empty())
                    info["userStrings"] = std::move(userStrings);
            }

            ON_BoundingBox bbox;
            if (!obj->GetTightBoundingBox(bbox) || !bbox.IsValid())
                bbox = obj->BoundingBox();
            if (bbox.IsValid())
            {
                info["bbox"]["min"] = { bbox.Min().x, bbox.Min().y, bbox.Min().z };
                info["bbox"]["max"] = { bbox.Max().x, bbox.Max().y, bbox.Max().z };
                defBbox.Union(bbox);
            }

            if (includeGeometry)
            {
                std::string geomType;
                auto detail = Handlers::CaptureGeometryDetail(obj, obj->Geometry(), pDoc, geomType);
                info["geometryType"] = geomType;
                info["geometry"] = std::visit(Serializer::GeometryDetailVisitor{}, detail);
            }

            objects.push_back(std::move(info));
        }

        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = blockName;
        wr.data["objectCount"] = static_cast<int>(objects.size());
        if (defBbox.IsValid())
        {
            wr.data["bbox"]["min"] = { defBbox.Min().x, defBbox.Min().y, defBbox.Min().z };
            wr.data["bbox"]["max"] = { defBbox.Max().x, defBbox.Max().y, defBbox.Max().z };
        }
        else
        {
            wr.data["bbox"] = nullptr;
        }
        wr.data["objects"] = std::move(objects);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/set-layers
void HandleBlockSetLayers(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    if (body.is_null() || body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }
    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Block name required");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const std::string blockName = body["name"].get<std::string>();
        const int idefIndex = FindDefByName(pDoc, blockName);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + blockName + "' not found");

        const CRhinoInstanceDefinition* def = pDoc->m_instance_definition_table[idefIndex];
        const int objectCount = def ? def->ObjectCount() : 0;

        int bulkLayerIndex = -1;
        if (body.contains("layer") && body["layer"].is_string())
        {
            bulkLayerIndex = Rook::Infrastructure::ResolveLayerRef(
                pDoc, body["layer"].get<std::string>(), "layer").index;
        }

        std::map<int, int> mappedLayers;
        if (body.contains("mappings") && body["mappings"].is_array())
        {
            for (const auto& mapping : body["mappings"])
            {
                const int idx = mapping.at("index").get<int>();
                if (idx < 0 || idx >= objectCount)
                    throw std::invalid_argument("Object index " + std::to_string(idx) + " out of range (block has " + std::to_string(objectCount) + " objects)");
                const std::string layerName = mapping.at("layer").get<std::string>();
                const int layerIndex = Rook::Infrastructure::ResolveLayerRef(
                    pDoc, layerName, "mappings[].layer").index;
                mappedLayers[idx] = layerIndex;
            }
        }

        if (bulkLayerIndex < 0 && mappedLayers.empty())
            throw std::invalid_argument("Either 'layer' or 'mappings' must be provided");

        UndoScope undo(pDoc, L"Set Block Object Layers");
        const bool modified = ModifyBlockDefinitionObjectAttributes(
            pDoc, idefIndex,
            [bulkLayerIndex, mappedLayers](int index, ON_3dmObjectAttributes& attrs)
            {
                if (bulkLayerIndex >= 0)
                    attrs.m_layer_index = bulkLayerIndex;
                auto it = mappedLayers.find(index);
                if (it != mappedLayers.end())
                    attrs.m_layer_index = it->second;
            });

        if (!modified)
            throw std::runtime_error("Failed to modify block '" + blockName + "'");

        const CRhinoInstanceDefinition* updated = pDoc->m_instance_definition_table[idefIndex];
        nlohmann::json objects = nlohmann::json::array();
        for (int i = 0; updated && i < updated->ObjectCount(); ++i)
        {
            const CRhinoObject* obj = updated->Object(i);
            if (!obj) continue;
            nlohmann::json item;
            item["index"] = i;
            item["id"] = UuidToString(obj->Attributes().m_uuid);
            item["type"] = GetObjectTypeName(obj);
            item["layer"] = GetLayerFullPath(pDoc, obj->Attributes().m_layer_index);
            objects.push_back(std::move(item));
        }

        pDoc->Redraw();
        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = blockName;
        wr.data["objectCount"] = static_cast<int>(objects.size());
        wr.data["objects"] = std::move(objects);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/set-materials
void HandleBlockSetMaterials(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    if (body.is_null() || body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }
    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Block name required");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const std::string blockName = body["name"].get<std::string>();
        const int idefIndex = FindDefByName(pDoc, blockName);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + blockName + "' not found");

        const CRhinoInstanceDefinition* def = pDoc->m_instance_definition_table[idefIndex];
        const int objectCount = def ? def->ObjectCount() : 0;

        int bulkMaterialIndex = -1;
        if (body.contains("material") && body["material"].is_string())
        {
            bulkMaterialIndex = FindMaterialIndex(pDoc, body["material"].get<std::string>());
            if (bulkMaterialIndex < 0)
                throw std::invalid_argument("Material '" + body["material"].get<std::string>() + "' not found");
        }

        std::map<int, int> mappedMaterials;
        if (body.contains("mappings") && body["mappings"].is_array())
        {
            for (const auto& mapping : body["mappings"])
            {
                const int idx = mapping.at("index").get<int>();
                if (idx < 0 || idx >= objectCount)
                    throw std::invalid_argument("Object index " + std::to_string(idx) + " out of range (block has " + std::to_string(objectCount) + " objects)");
                const std::string materialName = mapping.at("material").get<std::string>();
                const int materialIndex = FindMaterialIndex(pDoc, materialName);
                if (materialIndex < 0)
                    throw std::invalid_argument("Material '" + materialName + "' not found (mapping index " + std::to_string(idx) + ")");
                mappedMaterials[idx] = materialIndex;
            }
        }

        if (bulkMaterialIndex < 0 && mappedMaterials.empty())
            throw std::invalid_argument("Either 'material' or 'mappings' must be provided");

        UndoScope undo(pDoc, L"Set Block Object Materials");
        const bool modified = ModifyBlockDefinitionObjectAttributes(
            pDoc, idefIndex,
            [bulkMaterialIndex, mappedMaterials](int index, ON_3dmObjectAttributes& attrs)
            {
                if (bulkMaterialIndex >= 0)
                {
                    attrs.SetMaterialSource(ON::material_from_object);
                    attrs.m_material_index = bulkMaterialIndex;
                }
                auto it = mappedMaterials.find(index);
                if (it != mappedMaterials.end())
                {
                    attrs.SetMaterialSource(ON::material_from_object);
                    attrs.m_material_index = it->second;
                }
            });

        if (!modified)
            throw std::runtime_error("Failed to modify block '" + blockName + "'");

        const CRhinoInstanceDefinition* updated = pDoc->m_instance_definition_table[idefIndex];
        nlohmann::json objects = nlohmann::json::array();
        for (int i = 0; updated && i < updated->ObjectCount(); ++i)
        {
            const CRhinoObject* obj = updated->Object(i);
            if (!obj) continue;
            const ON_3dmObjectAttributes& attrs = obj->Attributes();
            nlohmann::json item;
            item["index"] = i;
            item["id"] = UuidToString(attrs.m_uuid);
            item["type"] = GetObjectTypeName(obj);
            item["layer"] = GetLayerFullPath(pDoc, attrs.m_layer_index);
            switch (attrs.MaterialSource())
            {
            case ON::material_from_object: item["materialSource"] = "MaterialFromObject"; break;
            case ON::material_from_parent: item["materialSource"] = "MaterialFromParent"; break;
            default: item["materialSource"] = "MaterialFromLayer"; break;
            }
            if (attrs.MaterialSource() == ON::material_from_object && attrs.m_material_index >= 0 && attrs.m_material_index < pDoc->m_material_table.MaterialCount())
                item["material"] = WideToUtf8(pDoc->m_material_table[attrs.m_material_index].Name());
            objects.push_back(std::move(item));
        }

        pDoc->Redraw();
        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = blockName;
        wr.data["objectCount"] = static_cast<int>(objects.size());
        wr.data["objects"] = std::move(objects);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/set-object-colors
void HandleBlockSetObjectColors(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    if (body.is_null() || body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }
    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Block name required");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const std::string blockName = body["name"].get<std::string>();
        const int idefIndex = FindDefByName(pDoc, blockName);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + blockName + "' not found");

        const CRhinoInstanceDefinition* def = pDoc->m_instance_definition_table[idefIndex];
        const int objectCount = def ? def->ObjectCount() : 0;

        ON_Color bulkColor = ON_Color::UnsetColor;
        const bool hasBulkColor = body.contains("color") && TryParseRgb(body["color"], bulkColor);

        std::map<int, ON_Color> mappedColors;
        if (body.contains("mappings") && body["mappings"].is_array())
        {
            for (const auto& mapping : body["mappings"])
            {
                const int idx = mapping.at("index").get<int>();
                if (idx < 0 || idx >= objectCount)
                    throw std::invalid_argument("Object index " + std::to_string(idx) + " out of range (block has " + std::to_string(objectCount) + " objects)");
                ON_Color color;
                if (TryParseRgb(mapping.at("color"), color))
                    mappedColors[idx] = color;
            }
        }

        if (!hasBulkColor && mappedColors.empty())
            throw std::invalid_argument("Either 'color' or 'mappings' must be provided");

        UndoScope undo(pDoc, L"Set Block Object Colors");
        const bool modified = ModifyBlockDefinitionObjectAttributes(
            pDoc, idefIndex,
            [hasBulkColor, bulkColor, mappedColors](int index, ON_3dmObjectAttributes& attrs)
            {
                if (hasBulkColor)
                {
                    attrs.SetColorSource(ON::color_from_object);
                    attrs.m_color = bulkColor;
                }
                auto it = mappedColors.find(index);
                if (it != mappedColors.end())
                {
                    attrs.SetColorSource(ON::color_from_object);
                    attrs.m_color = it->second;
                }
            });

        if (!modified)
            throw std::runtime_error("Failed to modify block '" + blockName + "'");

        const CRhinoInstanceDefinition* updated = pDoc->m_instance_definition_table[idefIndex];
        nlohmann::json objects = nlohmann::json::array();
        for (int i = 0; updated && i < updated->ObjectCount(); ++i)
        {
            const CRhinoObject* obj = updated->Object(i);
            if (!obj) continue;
            const ON_3dmObjectAttributes& attrs = obj->Attributes();
            nlohmann::json item;
            item["index"] = i;
            item["type"] = GetObjectTypeName(obj);
            item["color"] = { attrs.m_color.Red(), attrs.m_color.Green(), attrs.m_color.Blue() };
            switch (attrs.ColorSource())
            {
            case ON::color_from_object: item["colorSource"] = "ColorFromObject"; break;
            case ON::color_from_parent: item["colorSource"] = "ColorFromParent"; break;
            case ON::color_from_material: item["colorSource"] = "ColorFromMaterial"; break;
            default: item["colorSource"] = "ColorFromLayer"; break;
            }
            objects.push_back(std::move(item));
        }

        pDoc->Redraw();
        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = blockName;
        wr.data["objectCount"] = static_cast<int>(objects.size());
        wr.data["objects"] = std::move(objects);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/set-object-names
void HandleBlockSetObjectNames(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    if (body.is_null() || body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }
    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Block name required");
        return;
    }
    if (!body.contains("mappings") || !body["mappings"].is_array())
    {
        CRookServer::SendError(res, "'mappings' array required with {index, objectName} entries");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const std::string blockName = body["name"].get<std::string>();
        const int idefIndex = FindDefByName(pDoc, blockName);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + blockName + "' not found");

        const CRhinoInstanceDefinition* def = pDoc->m_instance_definition_table[idefIndex];
        const int objectCount = def ? def->ObjectCount() : 0;

        std::map<int, std::string> mappedNames;
        for (const auto& mapping : body["mappings"])
        {
            const int idx = mapping.at("index").get<int>();
            if (idx < 0 || idx >= objectCount)
                throw std::invalid_argument("Object index " + std::to_string(idx) + " out of range (block has " + std::to_string(objectCount) + " objects)");
            mappedNames[idx] = mapping.value("objectName", "");
        }

        UndoScope undo(pDoc, L"Set Block Object Names");
        const bool modified = ModifyBlockDefinitionObjectAttributes(
            pDoc, idefIndex,
            [mappedNames](int index, ON_3dmObjectAttributes& attrs)
            {
                auto it = mappedNames.find(index);
                if (it != mappedNames.end())
                    attrs.m_name = Utf8ToWide(it->second);
            });

        if (!modified)
            throw std::runtime_error("Failed to modify block '" + blockName + "'");

        const CRhinoInstanceDefinition* updated = pDoc->m_instance_definition_table[idefIndex];
        nlohmann::json objects = nlohmann::json::array();
        for (int i = 0; updated && i < updated->ObjectCount(); ++i)
        {
            const CRhinoObject* obj = updated->Object(i);
            if (!obj) continue;
            nlohmann::json item;
            item["index"] = i;
            item["type"] = GetObjectTypeName(obj);
            item["name"] = WideToUtf8(obj->Attributes().m_name);
            item["layer"] = GetLayerFullPath(pDoc, obj->Attributes().m_layer_index);
            objects.push_back(std::move(item));
        }

        pDoc->Redraw();
        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = blockName;
        wr.data["objectCount"] = static_cast<int>(objects.size());
        wr.data["objects"] = std::move(objects);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/set-object-user-strings
void HandleBlockSetObjectUserStrings(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    if (body.is_null() || body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }
    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Block name required");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const std::string blockName = body["name"].get<std::string>();
        const int idefIndex = FindDefByName(pDoc, blockName);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + blockName + "' not found");

        const CRhinoInstanceDefinition* def = pDoc->m_instance_definition_table[idefIndex];
        const int objectCount = def ? def->ObjectCount() : 0;

        std::map<std::string, std::string> bulkStrings;
        if (body.contains("userStrings") && body["userStrings"].is_object())
        {
            for (auto it = body["userStrings"].begin(); it != body["userStrings"].end(); ++it)
                bulkStrings[it.key()] = it.value().is_string() ? it.value().get<std::string>() : "";
        }

        std::map<int, std::map<std::string, std::string>> mappedStrings;
        if (body.contains("mappings") && body["mappings"].is_array())
        {
            for (const auto& mapping : body["mappings"])
            {
                const int idx = mapping.at("index").get<int>();
                if (idx < 0 || idx >= objectCount)
                    throw std::invalid_argument("Object index " + std::to_string(idx) + " out of range (block has " + std::to_string(objectCount) + " objects)");
                std::map<std::string, std::string> strings;
                if (mapping.contains("userStrings") && mapping["userStrings"].is_object())
                {
                    for (auto it = mapping["userStrings"].begin(); it != mapping["userStrings"].end(); ++it)
                        strings[it.key()] = it.value().is_string() ? it.value().get<std::string>() : "";
                }
                mappedStrings[idx] = std::move(strings);
            }
        }

        if (bulkStrings.empty() && mappedStrings.empty())
            throw std::invalid_argument("Either 'userStrings' or 'mappings' with userStrings must be provided");

        UndoScope undo(pDoc, L"Set Block Object User Strings");
        const bool modified = ModifyBlockDefinitionObjectAttributes(
            pDoc, idefIndex,
            [bulkStrings, mappedStrings](int index, ON_3dmObjectAttributes& attrs)
            {
                for (const auto& kv : bulkStrings)
                    attrs.SetUserString(Utf8ToWide(kv.first), Utf8ToWide(kv.second));

                auto it = mappedStrings.find(index);
                if (it != mappedStrings.end())
                {
                    for (const auto& kv : it->second)
                        attrs.SetUserString(Utf8ToWide(kv.first), Utf8ToWide(kv.second));
                }
            });

        if (!modified)
            throw std::runtime_error("Failed to modify block '" + blockName + "'");

        const CRhinoInstanceDefinition* updated = pDoc->m_instance_definition_table[idefIndex];
        nlohmann::json objects = nlohmann::json::array();
        for (int i = 0; updated && i < updated->ObjectCount(); ++i)
        {
            const CRhinoObject* obj = updated->Object(i);
            if (!obj) continue;
            nlohmann::json item;
            item["index"] = i;
            item["type"] = GetObjectTypeName(obj);
            item["userStrings"] = SerializeAttributeUserStrings(obj->Attributes());
            objects.push_back(std::move(item));
        }

        pDoc->Redraw();
        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = blockName;
        wr.data["objectCount"] = static_cast<int>(objects.size());
        wr.data["objects"] = std::move(objects);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// ─── Linked Blocks ──────────────────────────────────────────────────

// POST /block/link
void HandleBlockLink(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string path = body.value("path", "");
    if (path.empty()) { CRookServer::SendError(res, "File path required"); return; }
    {
        std::string pathErr = Rook::ValidateFilePath(path);
        if (!pathErr.empty()) { CRookServer::SendError(res, pathErr); return; }
    }
    {
        ON_wString wCheck = Utf8ToWide(path);
        if (!CRhinoFileUtilities::FileExists(wCheck))
        { CRookServer::SendError(res, "File not found: " + path); return; }
    }
    std::string name = body.value("name", "");

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, path, name]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Link block");

        std::string blockName = name;
        if (blockName.empty())
        {
            ON_wString wPath = Utf8ToWide(path);
            wPath.TrimRight(L"\\/");
            int lastSlash = wPath.ReverseFind(L'\\');
            int lastFSlash = wPath.ReverseFind(L'/');
            int pos = (std::max)(lastSlash, lastFSlash);
            ON_wString fname = (pos >= 0) ? wPath.Mid(pos + 1) : wPath;
            int dotPos = fname.ReverseFind(L'.');
            if (dotPos > 0) fname = fname.Left(dotPos);
            blockName = WideToUtf8(fname);
        }

        if (FindDefByName(pDoc, blockName) >= 0)
            throw std::invalid_argument("Block definition '" + blockName + "' already exists");

        // Use RunScript _-Insert to import as linked block
        ON_wString script;
        ON_wString wPath = Utf8ToWide(path);
        script.Format(L"_-Insert _File=\"%ls\" _Block _Enter _Enter",
            wPath.Array());
        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), script, 0);

        int newIdx = FindDefByName(pDoc, blockName);

        WriteResult wr;
        wr.success = (newIdx >= 0);
        wr.data["name"] = blockName;
        wr.data["sourcePath"] = path;
        if (newIdx >= 0)
        {
            const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[newIdx];
            wr.data["index"] = newIdx;
            wr.data["objectCount"] = pIdef ? pIdef->ObjectCount() : 0;
        }

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/refresh
void HandleBlockRefresh(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = body.value("name", "");
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Refresh linked block");

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        if (!pIdef) throw std::runtime_error("Block lookup failed");

        ON_wString linkedPath = pIdef->LinkedFilePath();
        if (linkedPath.IsEmpty())
            throw std::invalid_argument("Block '" + name + "' is not a linked block");

        bool refreshed = pDoc->m_instance_definition_table.UpdateLinkedInstanceDefinition(
            idefIndex, linkedPath, true, true);

        WriteResult wr;
        wr.success = refreshed;
        wr.data["name"] = name;
        wr.data["sourcePath"] = WideToUtf8(linkedPath);
        wr.data["refreshed"] = true;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/unlink
void HandleBlockUnlink(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = body.value("name", "");
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Unlink block");

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        if (!pIdef) throw std::runtime_error("Block lookup failed");

        ON_wString linkedPath = pIdef->LinkedFilePath();
        if (linkedPath.IsEmpty())
            throw std::invalid_argument("Block '" + name + "' is not a linked block");

        // Modify the definition to make it static (embedded)
        ON_InstanceDefinition idef_settings(*pIdef);
        idef_settings.SetInstanceDefinitionType(ON_InstanceDefinition::IDEF_UPDATE_TYPE::Static);

        bool ok = pDoc->m_instance_definition_table.ModifyInstanceDefinition(
            idef_settings, idefIndex,
            ON_InstanceDefinition::all_idef_settings, true);

        WriteResult wr;
        wr.success = ok;
        wr.data["name"] = name;
        wr.data["previousSourcePath"] = WideToUtf8(linkedPath);
        wr.data["unlinked"] = ok;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// ─── Utility ────────────────────────────────────────────────────────

// POST /block/purge
void HandleBlockPurge(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    bool purgeUnused = body.value("unused", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, purgeUnused]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Purge blocks");

        const CRhinoInstanceDefinitionTable& table = pDoc->m_instance_definition_table;
        nlohmann::json purgedNames = nlohmann::json::array();
        int purgedCount = 0;

        if (purgeUnused)
        {
            std::vector<int> toPurge;
            for (int i = 0; i < table.InstanceDefinitionCount(); ++i)
            {
                const CRhinoInstanceDefinition* pIdef = table[i];
                if (!pIdef || pIdef->IsDeleted()) continue;

                ON_SimpleArray<const CRhinoInstanceObject*> refs;
                pIdef->GetReferences(refs);

                if (refs.Count() == 0)
                {
                    toPurge.push_back(i);
                    purgedNames.push_back(WideToUtf8(pIdef->Name()));
                }
            }

            for (int j = static_cast<int>(toPurge.size()) - 1; j >= 0; --j)
            {
                pDoc->m_instance_definition_table.DeleteInstanceDefinition(
                    toPurge[j], false, true);
                ++purgedCount;
            }
        }

        int remaining = 0;
        for (int i = 0; i < table.InstanceDefinitionCount(); ++i)
        {
            const CRhinoInstanceDefinition* pIdef = table[i];
            if (pIdef && !pIdef->IsDeleted()) ++remaining;
        }

        WriteResult wr;
        wr.success = true;
        wr.data["purgedCount"] = purgedCount;
        wr.data["purgedNames"] = std::move(purgedNames);
        wr.data["remainingCount"] = remaining;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/duplicate
void HandleBlockDuplicate(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string sourceName = body.value("name", "");
    std::string newName = body.value("newName", "");
    if (sourceName.empty()) { CRookServer::SendError(res, "Source block name required"); return; }
    if (newName.empty()) { CRookServer::SendError(res, "New block name required"); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, sourceName, newName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Duplicate block");

        int srcIndex = FindDefByName(pDoc, sourceName);
        if (srcIndex < 0)
            throw std::invalid_argument("Block definition '" + sourceName + "' not found");

        if (FindDefByName(pDoc, newName) >= 0)
            throw std::invalid_argument("Block definition '" + newName + "' already exists");

        const CRhinoInstanceDefinition* pSrcDef = pDoc->m_instance_definition_table[srcIndex];
        if (!pSrcDef) throw std::runtime_error("Source block lookup failed");

        // Collect geometry objects from source
        ON_SimpleArray<const CRhinoObject*> srcObjects;
        pSrcDef->GetObjects(srcObjects);

        ON_InstanceDefinition new_idef;
        new_idef.SetName(Utf8ToWide(newName));
        new_idef.SetDescription(pSrcDef->Description());

        int newIndex = pDoc->m_instance_definition_table.AddInstanceDefinition(
            new_idef, srcObjects, false, false);

        if (newIndex < 0)
            throw std::runtime_error("Failed to create duplicate block");

        WriteResult wr;
        wr.success = true;
        wr.data["sourceName"] = sourceName;
        wr.data["newName"] = newName;
        wr.data["newIndex"] = newIndex;
        wr.data["objectCount"] = srcObjects.Count();

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// POST /block/rebase
// Move definition geometry in local space, then compensate every instance so
// world-space geometry stays fixed. Useful for Revit-exported blocks with
// baked absolute offsets (for example per-floor Z baked into the definition).
void HandleBlockRebase(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    const std::string name = body.value("name", "");
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    const std::string anchor = body.value("anchor", "bbox_min");
    const ON_3dPoint targetPoint = ParsePoint3dOrDefault(body, "targetPoint", ON_3dPoint::Origin);
    const bool dryRun = body.value("dryRun", true);
    const bool verbose = body.value("verbose", false);

    RebaseAxes axes;
    try
    {
        axes = ParseRebaseAxes(body);
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, anchor, targetPoint, dryRun, verbose, axes]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pDef = pDoc->m_instance_definition_table[idefIndex];
        if (!pDef)
            throw std::runtime_error("Block definition lookup failed");

        const int nullObjectCount = CountNullDefinitionObjects(pDef);
        if (nullObjectCount > 0)
        {
            throw std::runtime_error(
                "Block definition '" + name + "' contains " + std::to_string(nullObjectCount) +
                " null object slot(s) and cannot be rebased safely");
        }

        const ON_InstanceDefinition::IDEF_UPDATE_TYPE updateType = pDef->InstanceDefinitionType();
        if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked ||
            updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
        {
            throw std::invalid_argument(
                "Block definition '" + name + "' is linked. Rebase only supports embedded definitions");
        }

        const ON_BoundingBox bboxBefore = GetBlockDefinitionBoundingBox(pDef);
        if (!bboxBefore.IsValid())
            throw std::invalid_argument(
                "Block definition '" + name + "' has no valid geometry bounding box to rebase");

        const ON_3dPoint anchorPoint = GetRebaseAnchorPoint(bboxBefore, anchor);
        ON_3dVector definitionDelta = targetPoint - anchorPoint;
        if (!axes.x) definitionDelta.x = 0.0;
        if (!axes.y) definitionDelta.y = 0.0;
        if (!axes.z) definitionDelta.z = 0.0;

        constexpr double kRebaseEpsilon = 1e-9;
        const bool isNoOp =
            std::abs(definitionDelta.x) <= kRebaseEpsilon &&
            std::abs(definitionDelta.y) <= kRebaseEpsilon &&
            std::abs(definitionDelta.z) <= kRebaseEpsilon;
        if (isNoOp)
            throw std::invalid_argument("Requested rebase is a no-op for the selected axes");

        ON_SimpleArray<const CRhinoInstanceObject*> refs;
        pDef->GetReferences(refs);
        const int nestedUseCount = CountNestedDefinitionUses(pDoc, pDef);
        if (nestedUseCount > 0)
        {
            WriteResult wr;
            wr.success = false;
            wr.error =
                "Block definition '" + name + "' is used as a nested block " +
                std::to_string(nestedUseCount) +
                " time(s). Rebase currently supports top-level uses only";
            wr.data["blockName"] = name;
            wr.data["dryRun"] = dryRun;
            wr.data["executed"] = false;
            wr.data["nestedUseCount"] = nestedUseCount;
            wr.data["preservesWorldGeometry"] = false;
            wr.data["error"] = wr.error;
            return wr;
        }

        const ON_BoundingBox bboxAfter = TranslateBoundingBox(bboxBefore, definitionDelta);
        const ON_3dVector instanceCompensation = -definitionDelta;

        WriteResult wr;
        wr.success = true;
        wr.data["blockName"] = name;
        wr.data["dryRun"] = dryRun;
        wr.data["executed"] = !dryRun;
        wr.data["anchor"] = anchor;
        wr.data["axes"] = RebaseAxesToJson(axes);
        wr.data["anchorPoint"] = Point3dToJsonRounded(anchorPoint);
        wr.data["targetPoint"] = Point3dToJsonRounded(targetPoint);
        wr.data["definitionTranslation"] = Vector3dToJsonRounded(definitionDelta);
        wr.data["instanceCompensationTranslation"] = Vector3dToJsonRounded(instanceCompensation);
        wr.data["objectCount"] = pDef->ObjectCount();
        wr.data["instanceCount"] = refs.Count();
        wr.data["nestedUseCount"] = nestedUseCount;
        wr.data["bboxBefore"] = BoundingBoxToJsonRounded(bboxBefore);
        wr.data["bboxAfter"] = BoundingBoxToJsonRounded(bboxAfter);
        wr.data["preservesWorldGeometry"] = (nestedUseCount == 0);

        if (dryRun)
            return wr;

        struct InstanceData
        {
            ON_UUID oldId = ON_nil_uuid;
            ON_Xform oldXform = ON_Xform::IdentityTransformation;
            ON_3dmObjectAttributes attrs;
        };

        std::vector<InstanceData> instanceData;
        instanceData.reserve(refs.Count());
        for (int i = 0; i < refs.Count(); ++i)
        {
            const CRhinoInstanceObject* inst = refs[i];
            if (!inst)
                continue;

            InstanceData data;
            data.oldId = inst->Attributes().m_uuid;
            data.oldXform = inst->InstanceXform();
            data.attrs = inst->Attributes();
            instanceData.push_back(data);
        }

        // Pre-flight: reject definitions containing geometry types we can't
        // safely materialize into the document (ON_InstanceRef, SubD, text, etc.)
        const std::string materializeCheck = CheckDefinitionMaterializability(pDef);
        if (!materializeCheck.empty())
            throw std::invalid_argument(materializeCheck);

        const ON_Xform definitionTranslationXform = ON_Xform::TranslationTransformation(definitionDelta);

        // Everything from here is wrapped in a single undo record so that
        // temp-object creation, definition rewrite, temp cleanup, and instance
        // compensation are all covered by one Ctrl+Z.
        UndoScope undo(pDoc, L"Rebase block");

        // Materialize transformed objects into the document as temporary residents.
        // ModifyInstanceDefinitionGeometry retains references to these objects' geometry,
        // so they must be document-resident (soft-deletable) rather than heap-owned
        // (hard-freed). See HandleBlockReplaceGeometry for the proven pattern.
        ON_SimpleArray<const CRhinoObject*> docResidentObjects;
        std::vector<ON_UUID> tempObjectIds;
        if (!MaterializeTransformedBlockObjects(pDoc, pDef, definitionTranslationXform,
                docResidentObjects, tempObjectIds))
        {
            // Clean up any temp objects added before the failure
            for (const auto& tmpId : tempObjectIds)
                pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), tmpId));
            throw std::runtime_error("Failed to materialize translated block geometry");
        }

        if (!pDoc->m_instance_definition_table.ModifyInstanceDefinitionGeometry(
                idefIndex, docResidentObjects, false))
        {
            for (const auto& tmpId : tempObjectIds)
                pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), tmpId));
            throw std::runtime_error("Failed to update rebased geometry for block '" + name + "'");
        }

        // Soft-delete the temporary document objects. Their geometry data persists
        // in Rhino's undo buffer, keeping the definition's references valid.
        for (const auto& tmpId : tempObjectIds)
            pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), tmpId));

        const CRhinoInstanceDefinition* pUpdatedDef = pDoc->m_instance_definition_table[idefIndex];
        if (!pUpdatedDef)
            throw std::runtime_error("Updated block definition lookup failed after rebase");

        const ON_Xform instanceCompensationXform = ON_Xform::TranslationTransformation(instanceCompensation);
        nlohmann::json recreatedInstances = nlohmann::json::array();

        for (const auto& instance : instanceData)
        {
            pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), instance.oldId));

            // The compensation is post-multiplied because it lives in the
            // block definition's local coordinates, not world coordinates.
            const ON_Xform newXform = instance.oldXform * instanceCompensationXform;
            CRhinoInstanceObject* pNewInst =
                pDoc->m_instance_definition_table.CreateInstanceObject(
                    idefIndex, newXform, &instance.attrs, nullptr, false, false, true);

            if (!pNewInst)
            {
                wr.success = false;
                wr.error = "Failed to recreate compensated instance for block '" + name + "'";
                wr.data["partialRebase"] = true;
                wr.data["error"] = wr.error;
                return wr;
            }

            if (verbose)
            {
                recreatedInstances.push_back({
                    {"oldId", UuidToString(instance.oldId)},
                    {"newId", UuidToString(pNewInst->Attributes().m_uuid)}
                });
            }
        }

        wr.data["recreatedInstanceCount"] = static_cast<int>(instanceData.size());
        wr.data["bboxAfter"] = BoundingBoxToJsonRounded(GetBlockDefinitionBoundingBox(pUpdatedDef));
        if (verbose)
            wr.data["recreatedInstances"] = std::move(recreatedInstances);

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else if (!result.data.empty())
            CRookServer::SendErrorData(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// ─── Recursive Rebase Internals ─────────────────────────────────────

struct ParentRefEntry
{
    int parentDefIndex = -1;
    std::string parentDefName;
    std::string referencedChildName;
    int nestedRefsToLeaf = 0;
    int otherNestedRefs = 0;
    int plainObjects = 0;
    int totalObjects = 0;
    std::vector<int> leafRefObjectIndices;
};

struct RecursiveRebasePlan
{
    // Leaf
    int leafDefIndex = -1;
    std::string leafName;
    ON_BoundingBox leafBboxBefore;
    ON_BoundingBox leafBboxAfter;
    ON_3dVector definitionTranslation;
    ON_3dVector instanceCompensation;
    int leafObjectCount = 0;

    // Direct parent definitions referencing the leaf
    std::vector<ParentRefEntry> parentDefinitions;

    // Direct document instances of the leaf
    int directDocumentInstances = 0;

    // Plan hash
    std::string planHash;
};

// Find all definitions that directly contain ON_InstanceRef objects pointing at leafDef.
static std::vector<ParentRefEntry> FindDirectParentDefinitions(
    CRhinoDoc* pDoc,
    const CRhinoInstanceDefinition* leafDef,
    const std::string& leafName,
    bool verbose)
{
    std::vector<ParentRefEntry> parents;
    std::set<int> seenParentIndices;

    const int defCount = pDoc->m_instance_definition_table.InstanceDefinitionCount();
    for (int di = 0; di < defCount; ++di)
    {
        const CRhinoInstanceDefinition* pDef = pDoc->m_instance_definition_table[di];
        if (!pDef || pDef->IsDeleted())
            continue;
        if (pDef == leafDef)
            continue;

        int refsToLeaf = 0;
        int otherRefs = 0;
        int plainObjs = 0;
        std::vector<int> leafIndices;

        for (int oi = 0; oi < pDef->ObjectCount(); ++oi)
        {
            const CRhinoObject* obj = pDef->Object(oi);
            if (!obj) continue;

            const CRhinoInstanceObject* instObj = CRhinoInstanceObject::Cast(obj);
            if (instObj)
            {
                if (instObj->InstanceDefinition() == leafDef)
                {
                    refsToLeaf++;
                    if (verbose)
                        leafIndices.push_back(oi);
                }
                else
                {
                    otherRefs++;
                }
            }
            else
            {
                plainObjs++;
            }
        }

        if (refsToLeaf > 0 && seenParentIndices.insert(di).second)
        {
            ParentRefEntry entry;
            entry.parentDefIndex = di;
            entry.parentDefName = WideToUtf8(pDef->Name());
            entry.referencedChildName = leafName;
            entry.nestedRefsToLeaf = refsToLeaf;
            entry.otherNestedRefs = otherRefs;
            entry.plainObjects = plainObjs;
            entry.totalObjects = pDef->ObjectCount();
            entry.leafRefObjectIndices = std::move(leafIndices);
            parents.push_back(std::move(entry));
        }
    }

    return parents;
}

// Compute a stable hash over the plan for dry-run / execute verification.
static std::string ComputeRecursivePlanHash(
    const std::string& leafName,
    const std::vector<ParentRefEntry>& parents,
    const ON_3dVector& translation,
    int directDocumentInstanceCount)
{
    // Build a deterministic string: leaf + sorted parents with counts + direct instances + translation
    std::string input = leafName + "|";

    std::vector<std::string> parentKeys;
    parentKeys.reserve(parents.size());
    for (const auto& p : parents)
        parentKeys.push_back(p.parentDefName + ":" + std::to_string(p.nestedRefsToLeaf));
    std::sort(parentKeys.begin(), parentKeys.end());

    for (const auto& k : parentKeys)
        input += k + ";";

    input += "|di=" + std::to_string(directDocumentInstanceCount);

    input += "|" + std::to_string(translation.x) + ","
                 + std::to_string(translation.y) + ","
                 + std::to_string(translation.z);

    // Simple hash — FNV-1a 64-bit, formatted as hex
    uint64_t hash = 14695981039346656037ULL;
    for (char c : input)
    {
        hash ^= static_cast<uint64_t>(static_cast<unsigned char>(c));
        hash *= 1099511628211ULL;
    }

    char buf[17];
    snprintf(buf, sizeof(buf), "%016llx", static_cast<unsigned long long>(hash));
    return std::string(buf);
}

static nlohmann::json PlanToJson(const RecursiveRebasePlan& plan, bool verbose)
{
    nlohmann::json j;
    j["planHash"] = plan.planHash;

    j["leaf"] = {
        {"name", plan.leafName},
        {"bboxBefore", BoundingBoxToJsonRounded(plan.leafBboxBefore)},
        {"bboxAfter", BoundingBoxToJsonRounded(plan.leafBboxAfter)},
        {"definitionTranslation", Vector3dToJsonRounded(plan.definitionTranslation)},
        {"objectCount", plan.leafObjectCount}
    };

    nlohmann::json parentsJson = nlohmann::json::array();
    int totalNestedRefsCompensated = 0;
    for (const auto& p : plan.parentDefinitions)
    {
        nlohmann::json pj;
        pj["definitionName"] = p.parentDefName;
        pj["referencedChildName"] = p.referencedChildName;
        pj["nestedRefsToLeaf"] = p.nestedRefsToLeaf;
        pj["otherNestedRefs"] = p.otherNestedRefs;
        pj["plainObjects"] = p.plainObjects;
        pj["totalObjects"] = p.totalObjects;
        pj["compensationTranslation"] = Vector3dToJsonRounded(plan.instanceCompensation);
        if (verbose)
            pj["leafRefObjectIndices"] = p.leafRefObjectIndices;
        parentsJson.push_back(pj);
        totalNestedRefsCompensated += p.nestedRefsToLeaf;
    }
    j["parentDefinitions"] = parentsJson;

    j["directDocumentInstances"] = {
        {"definitionName", plan.leafName},
        {"instancesCompensated", plan.directDocumentInstances}
    };

    j["summary"] = {
        {"parentDefinitionsRewritten", static_cast<int>(plan.parentDefinitions.size())},
        {"totalNestedRefsCompensated", totalNestedRefsCompensated},
        {"directInstancesCompensated", plan.directDocumentInstances}
    };

    return j;
}

// POST /block/rebase-recursive
// Rebase a leaf definition and compensate direct parent definitions that
// reference it as a nested block, plus any direct document instances of the
// leaf. Does NOT walk grandparent or higher ancestors.
void HandleBlockRebaseRecursive(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    const std::string name = body.value("name", "");
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    const std::string anchor = body.value("anchor", "bbox_min");
    const ON_3dPoint targetPoint = ParsePoint3dOrDefault(body, "targetPoint", ON_3dPoint::Origin);
    const bool dryRun = body.value("dryRun", true);
    const bool verbose = body.value("verbose", false);
    const std::string expectedPlanHash = body.value("expectedPlanHash", "");

    RebaseAxes axes;
    try
    {
        axes = ParseRebaseAxes(body);
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, anchor, targetPoint, dryRun, verbose, expectedPlanHash, axes]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        // ─── Resolve leaf definition ─────────────────────────────
        const int leafDefIndex = FindDefByName(pDoc, name);
        if (leafDefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pLeafDef = pDoc->m_instance_definition_table[leafDefIndex];
        if (!pLeafDef)
            throw std::runtime_error("Block definition lookup failed");

        // ─── Build direct-referrer plan ──────────────────────────
        auto parentDefs = FindDirectParentDefinitions(pDoc, pLeafDef, name, verbose);

        if (parentDefs.empty())
            throw std::invalid_argument(
                "Definition '" + name + "' has no ancestor definitions; use rhino_block_rebase instead");

        ON_SimpleArray<const CRhinoInstanceObject*> leafDocRefs;
        pLeafDef->GetReferences(leafDocRefs);

        const ON_BoundingBox leafBbox = GetBlockDefinitionBoundingBox(pLeafDef);
        if (!leafBbox.IsValid())
            throw std::invalid_argument(
                "Block definition '" + name + "' has no valid geometry bounding box");

        const ON_3dPoint anchorPoint = GetRebaseAnchorPoint(leafBbox, anchor);
        ON_3dVector definitionDelta = targetPoint - anchorPoint;
        if (!axes.x) definitionDelta.x = 0.0;
        if (!axes.y) definitionDelta.y = 0.0;
        if (!axes.z) definitionDelta.z = 0.0;

        constexpr double kRebaseEpsilon = 1e-9;
        const bool isNoOp =
            std::abs(definitionDelta.x) <= kRebaseEpsilon &&
            std::abs(definitionDelta.y) <= kRebaseEpsilon &&
            std::abs(definitionDelta.z) <= kRebaseEpsilon;
        if (isNoOp)
            throw std::invalid_argument("Requested rebase is a no-op for the selected axes");

        RecursiveRebasePlan plan;
        plan.leafDefIndex = leafDefIndex;
        plan.leafName = name;
        plan.leafBboxBefore = leafBbox;
        plan.leafBboxAfter = TranslateBoundingBox(leafBbox, definitionDelta);
        plan.definitionTranslation = definitionDelta;
        plan.instanceCompensation = -definitionDelta;
        plan.leafObjectCount = pLeafDef->ObjectCount();
        plan.parentDefinitions = std::move(parentDefs);
        plan.directDocumentInstances = leafDocRefs.Count();
        plan.planHash = ComputeRecursivePlanHash(name, plan.parentDefinitions, definitionDelta, leafDocRefs.Count());

        // ─── Preflight validation ────────────────────────────────

        // Leaf validation
        {
            const auto updateType = pLeafDef->InstanceDefinitionType();
            if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked ||
                updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
                throw std::invalid_argument("Leaf definition '" + name + "' is linked; rebase only supports embedded definitions");

            const int nullCount = CountNullDefinitionObjects(pLeafDef);
            if (nullCount > 0)
                throw std::runtime_error("Leaf definition '" + name + "' contains " +
                    std::to_string(nullCount) + " null object slot(s)");

            // Check materializability — plain geometry must be materializable,
            // ON_InstanceRef objects are handled by CreateInstanceObject in leaf mode
            std::set<std::string> leafUnsupported;
            for (int oi = 0; oi < pLeafDef->ObjectCount(); ++oi)
            {
                const CRhinoObject* obj = pLeafDef->Object(oi);
                if (!obj || !obj->Geometry()) continue;
                if (CRhinoInstanceObject::Cast(obj)) continue;
                if (!CanMaterializeGeometry(obj->Geometry()))
                    leafUnsupported.insert(GeometryTypeName(obj->Geometry()));
            }
            if (!leafUnsupported.empty())
            {
                std::string typeList;
                for (const auto& t : leafUnsupported)
                {
                    if (!typeList.empty()) typeList += ", ";
                    typeList += t;
                }
                throw std::invalid_argument("Leaf definition contains unsupported types: " + typeList);
            }
        }

        // Parent validation
        for (const auto& parent : plan.parentDefinitions)
        {
            const CRhinoInstanceDefinition* pParentDef = pDoc->m_instance_definition_table[parent.parentDefIndex];
            if (!pParentDef)
                throw std::runtime_error("Parent definition '" + parent.parentDefName + "' lookup failed");

            const auto updateType = pParentDef->InstanceDefinitionType();
            if (updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked ||
                updateType == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
                throw std::invalid_argument("Parent definition '" + parent.parentDefName + "' is linked; cannot rewrite");

            const int nullCount = CountNullDefinitionObjects(pParentDef);
            if (nullCount > 0)
                throw std::runtime_error("Parent definition '" + parent.parentDefName + "' contains " +
                    std::to_string(nullCount) + " null object slot(s)");

            // Check materializability — plain geometry must be materializable,
            // ON_InstanceRef objects are handled specially by the parent rewrite path
            std::set<std::string> unsupportedTypes;
            for (int oi = 0; oi < pParentDef->ObjectCount(); ++oi)
            {
                const CRhinoObject* obj = pParentDef->Object(oi);
                if (!obj || !obj->Geometry()) continue;

                // Instance refs are handled by CreateInstanceObject, not AddGeometryToDoc
                if (CRhinoInstanceObject::Cast(obj))
                    continue;

                if (!CanMaterializeGeometry(obj->Geometry()))
                    unsupportedTypes.insert(GeometryTypeName(obj->Geometry()));
            }
            if (!unsupportedTypes.empty())
            {
                std::string typeList;
                for (const auto& t : unsupportedTypes)
                {
                    if (!typeList.empty()) typeList += ", ";
                    typeList += t;
                }
                throw std::invalid_argument("Parent definition '" + parent.parentDefName +
                    "' contains unsupported types: " + typeList);
            }
        }

        // ─── Dry-run: return the plan ────────────────────────────
        if (dryRun)
        {
            WriteResult wr;
            wr.success = true;
            wr.data = PlanToJson(plan, verbose);
            wr.data["dryRun"] = true;
            wr.data["executed"] = false;
            return wr;
        }

        // ─── Execute: verify planHash ────────────────────────────
        if (expectedPlanHash.empty())
            throw std::invalid_argument("expectedPlanHash required for execute; run dry-run first");

        if (expectedPlanHash != plan.planHash)
            throw std::invalid_argument("Plan changed since dry-run; re-run dry-run (expected: " +
                expectedPlanHash + ", got: " + plan.planHash + ")");

        // Execute-time re-resolution: verify all definitions still exist and haven't changed
        {
            const CRhinoInstanceDefinition* pLeafCheck = pDoc->m_instance_definition_table[leafDefIndex];
            if (!pLeafCheck || pLeafCheck->IsDeleted())
                throw std::runtime_error("Leaf definition '" + name + "' no longer exists");

            for (const auto& parent : plan.parentDefinitions)
            {
                const CRhinoInstanceDefinition* pParentCheck = pDoc->m_instance_definition_table[parent.parentDefIndex];
                if (!pParentCheck || pParentCheck->IsDeleted())
                    throw std::runtime_error("Parent definition '" + parent.parentDefName +
                        "' no longer exists or changed state");

                const auto ut = pParentCheck->InstanceDefinitionType();
                if (ut == ON_InstanceDefinition::IDEF_UPDATE_TYPE::Linked ||
                    ut == ON_InstanceDefinition::IDEF_UPDATE_TYPE::LinkedAndEmbedded)
                    throw std::runtime_error("Parent definition '" + parent.parentDefName +
                        "' changed to linked state since dry-run");
            }
        }

        // ─── Execute under single UndoScope ─────────────────────

        UndoScope undo(pDoc, L"Recursive block rebase");

        const ON_Xform leafTranslationXform = ON_Xform::TranslationTransformation(plan.definitionTranslation);
        const ON_Xform compensationXform = ON_Xform::TranslationTransformation(plan.instanceCompensation);

        // Helper lambda: clean up temp objects on failure
        auto cleanupTemps = [&](const std::vector<ON_UUID>& ids) {
            for (const auto& id : ids)
                pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), id));
        };

        // ─── Step 3a: Rebase the leaf definition ────────────────
        {
            ON_SimpleArray<const CRhinoObject*> leafDocObjects;
            std::vector<ON_UUID> leafTempIds;
            // Leaf mode: apply geometry translation to all objects (plain + instance refs)
            if (!MaterializeDefinitionObjects(pDoc, pLeafDef, leafTranslationXform,
                    -1, ON_Xform::IdentityTransformation, leafDocObjects, leafTempIds))
            {
                cleanupTemps(leafTempIds);
                throw std::runtime_error("Failed to materialize leaf definition geometry");
            }

            if (!pDoc->m_instance_definition_table.ModifyInstanceDefinitionGeometry(
                    leafDefIndex, leafDocObjects, false))
            {
                cleanupTemps(leafTempIds);
                throw std::runtime_error("Failed to update leaf definition geometry");
            }

            cleanupTemps(leafTempIds);
        }

        // ─── Step 3b: Rewrite each parent definition ────────────
        int totalNestedRefsCompensated = 0;
        for (const auto& parentEntry : plan.parentDefinitions)
        {
            const CRhinoInstanceDefinition* pParentDef =
                pDoc->m_instance_definition_table[parentEntry.parentDefIndex];
            if (!pParentDef)
                throw std::runtime_error("Parent definition '" + parentEntry.parentDefName +
                    "' disappeared during execute");

            ON_SimpleArray<const CRhinoObject*> parentDocObjects;
            std::vector<ON_UUID> parentTempIds;
            // Parent mode: identity geometry xform, compensate only refs to the leaf
            if (!MaterializeDefinitionObjects(pDoc, pParentDef, ON_Xform::IdentityTransformation,
                    leafDefIndex, compensationXform, parentDocObjects, parentTempIds))
            {
                cleanupTemps(parentTempIds);
                throw std::runtime_error("Failed to materialize parent definition '" +
                    parentEntry.parentDefName + "'");
            }

            if (!pDoc->m_instance_definition_table.ModifyInstanceDefinitionGeometry(
                    parentEntry.parentDefIndex, parentDocObjects, false))
            {
                cleanupTemps(parentTempIds);
                throw std::runtime_error("Failed to update parent definition '" +
                    parentEntry.parentDefName + "'");
            }

            cleanupTemps(parentTempIds);
            totalNestedRefsCompensated += parentEntry.nestedRefsToLeaf;
        }

        // ─── Step 3c: Compensate direct document instances of the leaf ───
        int directInstancesCompensated = 0;
        if (leafDocRefs.Count() > 0)
        {
            struct LeafInstanceData
            {
                ON_UUID oldId = ON_nil_uuid;
                ON_Xform oldXform = ON_Xform::IdentityTransformation;
                ON_3dmObjectAttributes attrs;
            };

            std::vector<LeafInstanceData> leafInstances;
            leafInstances.reserve(leafDocRefs.Count());
            for (int i = 0; i < leafDocRefs.Count(); ++i)
            {
                const CRhinoInstanceObject* inst = leafDocRefs[i];
                if (!inst) continue;
                LeafInstanceData d;
                d.oldId = inst->Attributes().m_uuid;
                d.oldXform = inst->InstanceXform();
                d.attrs = inst->Attributes();
                leafInstances.push_back(d);
            }

            for (const auto& d : leafInstances)
            {
                pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), d.oldId));

                const ON_Xform newXform = d.oldXform * compensationXform;
                CRhinoInstanceObject* pNewInst =
                    pDoc->m_instance_definition_table.CreateInstanceObject(
                        leafDefIndex, newXform, &d.attrs, nullptr, false, false, true);

                if (!pNewInst)
                    throw std::runtime_error("Failed to recreate direct document instance of leaf '" + name + "'");

                directInstancesCompensated++;
            }
        }

        // ─── Build execute result ────────────────────────────────

        // Re-read leaf bbox after mutation
        const CRhinoInstanceDefinition* pLeafAfter = pDoc->m_instance_definition_table[leafDefIndex];
        if (pLeafAfter)
            plan.leafBboxAfter = GetBlockDefinitionBoundingBox(pLeafAfter);

        WriteResult wr;
        wr.success = true;
        wr.data = PlanToJson(plan, verbose);
        wr.data["dryRun"] = false;
        wr.data["executed"] = true;
        wr.data["summary"]["totalNestedRefsCompensated"] = totalNestedRefsCompensated;
        wr.data["summary"]["directInstancesCompensated"] = directInstancesCompensated;

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else if (!result.data.empty())
            CRookServer::SendErrorData(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// GET+POST /block/nested
void HandleBlockNested(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string name = GetBlockName(req, body);
    if (name.empty()) { CRookServer::SendError(res, "Block name required"); return; }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        int idefIndex = FindDefByName(pDoc, name);
        if (idefIndex < 0)
            throw std::invalid_argument("Block definition '" + name + "' not found");

        const CRhinoInstanceDefinition* pIdef = pDoc->m_instance_definition_table[idefIndex];
        if (!pIdef) throw std::runtime_error("Block lookup failed");

        std::set<int> visited;
        nlohmann::json hierarchy = BuildNestedHierarchy(pDoc, pIdef, visited);

        WriteResult wr;
        wr.success = true;
        wr.data = std::move(hierarchy);

        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// ─── POST /block/merge ─────────────────────────────────────────
// Repoint instances of source definitions to a single target definition.
// Supports dry-run for review. Execute mode is single-undo recoverable, not transactional.

void HandleBlockMerge(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string targetName = body.value("target", "");
    if (targetName.empty()) { CRookServer::SendError(res, "Missing required parameter 'target'"); return; }

    std::vector<std::string> sourceNames;
    if (body.contains("sources") && body["sources"].is_array())
    {
        std::set<std::string> seen;
        for (const auto& el : body["sources"])
        {
            if (!el.is_string()) continue;
            std::string s = el.get<std::string>();
            if (seen.insert(s).second)
                sourceNames.push_back(s);
        }
    }
    if (sourceNames.empty()) { CRookServer::SendError(res, "Missing or empty 'sources' array"); return; }

    bool dryRun = body.value("dryRun", true);
    bool verbose = body.value("verbose", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, targetName, sourceNames, dryRun, verbose]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        // Resolve target
        int targetIdx = FindDefByName(pDoc, targetName);
        if (targetIdx < 0)
            throw std::invalid_argument("Target block definition '" + targetName + "' not found");
        const CRhinoInstanceDefinition* pTargetDef = pDoc->m_instance_definition_table[targetIdx];
        if (!pTargetDef) throw std::runtime_error("Target block lookup failed");

        // Count target instances before merge
        ON_SimpleArray<const CRhinoInstanceObject*> targetRefs;
        pTargetDef->GetReferences(targetRefs);
        int instanceCountBefore = targetRefs.Count();

        // Resolve sources
        nlohmann::json sourcesResult = nlohmann::json::array();
        nlohmann::json errors = nlohmann::json::array();
        int totalInstancesAffected = 0;

        struct SourceInfo {
            std::string name;
            std::string id;
            int defIndex;
            int instanceCount;
            std::vector<std::string> instanceIds;
        };
        std::vector<SourceInfo> validSources;

        for (const auto& srcName : sourceNames)
        {
            if (srcName == targetName)
            {
                errors.push_back({ {"name", srcName}, {"error", "target_in_sources"} });
                continue;
            }

            int srcIdx = FindDefByName(pDoc, srcName);
            if (srcIdx < 0)
            {
                errors.push_back({ {"name", srcName}, {"error", "not_found"} });
                continue;
            }
            const CRhinoInstanceDefinition* pSrcDef = pDoc->m_instance_definition_table[srcIdx];
            if (!pSrcDef)
            {
                errors.push_back({ {"name", srcName}, {"error", "lookup_failed"} });
                continue;
            }

            ON_SimpleArray<const CRhinoInstanceObject*> srcRefs;
            pSrcDef->GetReferences(srcRefs);

            SourceInfo info;
            info.name = srcName;
            info.id = UuidToString(pSrcDef->Id());
            info.defIndex = srcIdx;
            info.instanceCount = srcRefs.Count();

            if (verbose)
            {
                for (int i = 0; i < srcRefs.Count(); ++i)
                {
                    if (srcRefs[i])
                        info.instanceIds.push_back(UuidToString(srcRefs[i]->Attributes().m_uuid));
                }
            }

            validSources.push_back(std::move(info));
        }

        if (validSources.empty())
        {
            WriteResult wr;
            wr.success = false;
            wr.error = "No valid source definitions found";
            return wr;
        }

        // Dry run: report counts only
        if (dryRun)
        {
            for (const auto& src : validSources)
            {
                nlohmann::json sj;
                sj["name"] = src.name;
                sj["id"] = src.id;
                sj["instanceCount"] = src.instanceCount;
                sj["purgeable"] = true;  // would be purgeable after merge
                if (verbose)
                    sj["instanceIds"] = src.instanceIds;
                sourcesResult.push_back(sj);
                totalInstancesAffected += src.instanceCount;
            }

            WriteResult wr;
            wr.data["dryRun"] = true;
            wr.data["executed"] = false;
            wr.data["target"] = {
                {"name", targetName},
                {"id", UuidToString(pTargetDef->Id())},
                {"instanceCountBefore", instanceCountBefore},
                {"instanceCountAfter", instanceCountBefore + totalInstancesAffected}
            };
            wr.data["sources"] = sourcesResult;
            wr.data["totalInstancesAffected"] = totalInstancesAffected;
            wr.data["errors"] = errors;
            return wr;
        }

        // Execute: repoint instances under a single UndoScope.
        // This is single-undo recoverable, not transactional — if a replacement
        // fails mid-way, partial mutations remain but can be undone as one step
        // via Rhino's undo system.
        UndoScope undo(pDoc, L"Block merge");

        for (auto& src : validSources)
        {
            const CRhinoInstanceDefinition* pSrcDef = pDoc->m_instance_definition_table[src.defIndex];
            if (!pSrcDef) continue;

            ON_SimpleArray<const CRhinoInstanceObject*> srcRefs;
            pSrcDef->GetReferences(srcRefs);
            src.instanceCount = srcRefs.Count();

            // Collect instance data before mutation (refs become invalid after delete)
            struct InstanceData {
                ON_UUID id;
                ON_Xform xform;
                ON_3dmObjectAttributes attrs;
            };
            std::vector<InstanceData> instData;
            instData.reserve(srcRefs.Count());
            for (int i = 0; i < srcRefs.Count(); ++i)
            {
                const CRhinoInstanceObject* inst = srcRefs[i];
                if (!inst) continue;
                InstanceData d;
                d.id = inst->Attributes().m_uuid;
                d.xform = inst->InstanceXform();
                d.attrs = inst->Attributes();
                instData.push_back(d);
            }

            if (verbose)
            {
                src.instanceIds.clear();
                for (const auto& d : instData)
                    src.instanceIds.push_back(UuidToString(d.id));
            }

            // Delete old, create new — same pattern as HandleBlockReplaceInstance
            for (const auto& d : instData)
            {
                pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), d.id));

                CRhinoInstanceObject* pNewInst =
                    pDoc->m_instance_definition_table.CreateInstanceObject(
                        targetIdx, d.xform, &d.attrs, nullptr, false, false, true);

                if (!pNewInst)
                {
                    // Stop on failure. Partial mutations are single-undo recoverable.
                    WriteResult wr;
                    wr.success = false;
                    wr.error = "Failed to create replacement instance for source '" + src.name + "'";
                    wr.data["partialMerge"] = true;
                    wr.data["error"] = wr.error;
                    return wr;
                }
            }

            totalInstancesAffected += src.instanceCount;
        }

        pDoc->Redraw();

        // Build response — re-check purgeable status after mutation
        for (const auto& src : validSources)
        {
            const CRhinoInstanceDefinition* pSrcDef = pDoc->m_instance_definition_table[src.defIndex];
            ON_SimpleArray<const CRhinoInstanceObject*> remainingRefs;
            if (pSrcDef) pSrcDef->GetReferences(remainingRefs);

            nlohmann::json sj;
            sj["name"] = src.name;
            sj["id"] = src.id;
            sj["instanceCount"] = src.instanceCount;
            sj["purgeable"] = (remainingRefs.Count() == 0);
            if (verbose)
                sj["instanceIds"] = src.instanceIds;
            sourcesResult.push_back(sj);
        }

        // Re-count target instances after merge
        ON_SimpleArray<const CRhinoInstanceObject*> targetRefsAfter;
        pTargetDef->GetReferences(targetRefsAfter);

        WriteResult wr;
        wr.data["dryRun"] = false;
        wr.data["executed"] = true;
        wr.data["target"] = {
            {"name", targetName},
            {"id", UuidToString(pTargetDef->Id())},
            {"instanceCountBefore", instanceCountBefore},
            {"instanceCountAfter", targetRefsAfter.Count()}
        };
        wr.data["sources"] = sourcesResult;
        wr.data["totalInstancesAffected"] = totalInstancesAffected;
        wr.data["errors"] = errors;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else if (!result.data.empty())
            CRookServer::SendErrorData(res, result.data);  // partial merge with context
        else
            CRookServer::SendError(res, result.error);      // simple error message
    }
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// ─── POST /block/compare ───────────────────────────────────────
// Bulk geometric comparison of block definitions in a single main-thread pass.
// Returns shape metrics, type histograms, area/volume, and nested instance data.

// FNV-1a hash for deterministic, cheap hashing of sorted ID strings.
static uint64_t FnvHash(const std::string& str)
{
    uint64_t hash = 14695981039346656037ULL;
    for (char c : str)
    {
        hash ^= static_cast<uint64_t>(static_cast<unsigned char>(c));
        hash *= 1099511628211ULL;
    }
    return hash;
}

void HandleBlockCompare(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Parse and deduplicate names (preserve input order for first occurrence)
    std::vector<std::string> names;
    if (body.contains("names") && body["names"].is_array())
    {
        std::set<std::string> seen;
        for (const auto& el : body["names"])
        {
            if (!el.is_string()) continue;
            std::string s = el.get<std::string>();
            if (seen.insert(s).second)
                names.push_back(s);
        }
    }
    if (names.empty()) { CRookServer::SendError(res, "Missing or empty 'names' array"); return; }

    bool includeNestedOriginalIds = body.value("includeNestedOriginalIds", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, names, includeNestedOriginalIds]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        nlohmann::json definitions = nlohmann::json::array();
        nlohmann::json errors = nlohmann::json::array();

        for (const auto& name : names)
        {
            int idefIndex = FindDefByName(pDoc, name);
            if (idefIndex < 0)
            {
                errors.push_back({ {"name", name}, {"error", "not_found"} });
                continue;
            }

            const CRhinoInstanceDefinition* pDef = pDoc->m_instance_definition_table[idefIndex];
            if (!pDef)
            {
                errors.push_back({ {"name", name}, {"error", "lookup_failed"} });
                continue;
            }

            // Instance count
            ON_SimpleArray<const CRhinoInstanceObject*> refs;
            pDef->GetReferences(refs);
            int instanceCount = refs.Count();

            // Iterate constituent objects
            int objectCount = pDef->ObjectCount();
            std::map<std::string, int> typeHistogram;
            ON_BoundingBox aggBbox = ON_BoundingBox::EmptyBoundingBox;
            double totalArea = 0;
            double totalVolume = 0;
            int areaMeasuredCount = 0;
            int volumeMeasuredCount = 0;
            bool hasAnyArea = false;
            bool hasAnyVolume = false;
            int nestedInstanceCount = 0;
            std::vector<std::string> nestedOriginalIds;

            for (int i = 0; i < objectCount; ++i)
            {
                const CRhinoObject* obj = pDef->Object(i);
                if (!obj) continue;

                // Type histogram
                std::string typeName = GetObjectTypeName(obj);
                typeHistogram[typeName]++;

                const ON_Geometry* geom = obj->Geometry();
                if (!geom) continue;

                // Bbox union — use tight bounds for representation-independent comparison.
                // Object-level GetTightBoundingBox includes instance transforms for
                // nested block refs; geometry-level would miss them.
                ON_BoundingBox objBbox;
                if (!obj->GetTightBoundingBox(objBbox) || !objBbox.IsValid())
                    objBbox = obj->BoundingBox();
                if (objBbox.IsValid())
                    aggBbox.Union(objBbox);

                // Brep area/volume (matching GeometryHandler.cpp pattern)
                if (const ON_Brep* brep = ON_Brep::Cast(geom))
                {
                    {
                        ON_MassProperties mp;
                        if (brep->AreaMassProperties(mp, true, false, false, false))
                        {
                            double a = mp.Area();
                            if (!std::isnan(a))
                            {
                                totalArea += a;
                                areaMeasuredCount++;
                                hasAnyArea = true;
                            }
                        }
                    }

                    if (brep->IsSolid())
                    {
                        ON_MassProperties mp;
                        if (brep->VolumeMassProperties(mp, true, false, false, false))
                        {
                            double v = mp.Volume();
                            if (!std::isnan(v))
                            {
                                totalVolume += v;
                                volumeMeasuredCount++;
                                hasAnyVolume = true;
                            }
                        }
                    }
                }

                // Nested instance tracking
                if (CRhinoInstanceObject::Cast(obj))
                {
                    nestedInstanceCount++;

                    // Read $block-instance-original-object-id$ user string
                    ON_wString origIdValue;
                    if (obj->Attributes().GetUserString(
                        L"$block-instance-original-object-id$", origIdValue))
                    {
                        std::string idStr = WideToUtf8(origIdValue);
                        if (!idStr.empty())
                            nestedOriginalIds.push_back(idStr);
                    }
                }
            }

            // Shape metrics from aggregate bbox
            nlohmann::json metricsJson = nullptr;
            std::string shapeClass = "unknown";
            if (aggBbox.IsValid())
            {
                std::array<double, 3> bmin = {
                    aggBbox.Min().x, aggBbox.Min().y, aggBbox.Min().z };
                std::array<double, 3> bmax = {
                    aggBbox.Max().x, aggBbox.Max().y, aggBbox.Max().z };

                Rook::ShapeMetrics m = Rook::ComputeMetrics(bmin, bmax);
                shapeClass = Rook::DetermineShapeClass(m);

                metricsJson = {
                    {"maxDim", RoundTo(m.maxDim, 2)},
                    {"midDim", RoundTo(m.midDim, 2)},
                    {"minDim", RoundTo(m.minDim, 2)},
                    {"elongation", RoundTo(m.elongation, 2)},
                    {"flatness", RoundTo(m.flatness, 2)},
                    {"thinness", RoundTo(m.thinness, 3)},
                    {"primaryAxis", m.primaryAxis},
                    {"thinAxis", m.thinAxis},
                    {"isVertical", m.isVertical},
                    {"isHorizontal", m.isHorizontal}
                };
            }

            // Nested original IDs hash — deterministic FNV-1a over sorted IDs
            std::sort(nestedOriginalIds.begin(), nestedOriginalIds.end());
            std::string nestedOriginalIdsHash;
            if (!nestedOriginalIds.empty())
            {
                std::string concat;
                for (const auto& id : nestedOriginalIds)
                {
                    if (!concat.empty()) concat += ',';
                    concat += id;
                }
                uint64_t hash = FnvHash(concat);
                char buf[17];
                snprintf(buf, sizeof(buf), "%016llx", static_cast<unsigned long long>(hash));
                nestedOriginalIdsHash = buf;
            }

            // Build definition output
            nlohmann::json defJson;
            defJson["name"] = name;
            defJson["id"] = UuidToString(pDef->Id());
            defJson["objectCount"] = objectCount;
            defJson["instanceCount"] = instanceCount;

            if (aggBbox.IsValid())
            {
                defJson["bbox"] = {
                    {"min", {RoundTo(aggBbox.Min().x, 4), RoundTo(aggBbox.Min().y, 4), RoundTo(aggBbox.Min().z, 4)}},
                    {"max", {RoundTo(aggBbox.Max().x, 4), RoundTo(aggBbox.Max().y, 4), RoundTo(aggBbox.Max().z, 4)}}
                };
            }
            else
            {
                defJson["bbox"] = nullptr;
            }

            defJson["typeHistogram"] = typeHistogram;
            defJson["totalArea"] = hasAnyArea ? nlohmann::json(RoundTo(totalArea, 4)) : nlohmann::json(nullptr);
            defJson["totalVolume"] = hasAnyVolume ? nlohmann::json(RoundTo(totalVolume, 4)) : nlohmann::json(nullptr);
            defJson["areaMeasuredObjectCount"] = areaMeasuredCount;
            defJson["volumeMeasuredObjectCount"] = volumeMeasuredCount;
            defJson["nestedInstanceCount"] = nestedInstanceCount;
            defJson["nestedOriginalIdsCount"] = static_cast<int>(nestedOriginalIds.size());
            defJson["nestedOriginalIdsHash"] = nestedOriginalIdsHash.empty() ? nlohmann::json(nullptr) : nlohmann::json(nestedOriginalIdsHash);
            defJson["nestedOriginalIds"] = includeNestedOriginalIds
                ? nlohmann::json(nestedOriginalIds)
                : nlohmann::json(nullptr);
            defJson["metrics"] = metricsJson;
            defJson["shapeClass"] = shapeClass;

            definitions.push_back(std::move(defJson));
        }

        // Call succeeds as long as at least one definition resolved
        if (definitions.empty() && !errors.empty())
        {
            WriteResult wr;
            wr.success = false;
            wr.error = "No valid block definitions found";
            return wr;
        }

        WriteResult wr;
        wr.data["definitions"] = std::move(definitions);
        wr.data["count"] = static_cast<int>(wr.data["definitions"].size());
        wr.data["errors"] = std::move(errors);
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
    catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }
}

// ─── GET /block/layer-census — Layer usage across all block definitions ──

void HandleBlockLayerCensus(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const CRhinoInstanceDefinitionTable& idefTable = pDoc->m_instance_definition_table;
        nlohmann::json blocks = nlohmann::json::array();

        for (int d = 0; d < idefTable.InstanceDefinitionCount(); ++d)
        {
            const CRhinoInstanceDefinition* idef = idefTable[d];
            if (!idef || idef->IsDeleted()) continue;

            ON_SimpleArray<const CRhinoObject*> objArray;
            idef->GetObjects(objArray);

            if (objArray.Count() == 0) continue;

            // Count objects per layer within this block
            std::map<int, int> layerCounts;
            for (int j = 0; j < objArray.Count(); ++j)
            {
                if (!objArray[j]) continue;
                layerCounts[objArray[j]->Attributes().m_layer_index]++;
            }

            // Resolve layer indices to full paths
            nlohmann::json layerUsage = nlohmann::json::array();
            for (const auto& [layerIdx, count] : layerCounts)
            {
                nlohmann::json entry;
                if (layerIdx >= 0 && layerIdx < pDoc->m_layer_table.LayerCount())
                {
                    ON_wString fullPath;
                    pDoc->m_layer_table.GetLayerPathName(layerIdx, fullPath);
                    entry["layer"] = WideToUtf8(fullPath);
                    entry["layerIndex"] = layerIdx;
                }
                else
                {
                    entry["layer"] = "(invalid index " + std::to_string(layerIdx) + ")";
                    entry["layerIndex"] = layerIdx;
                }
                entry["objectCount"] = count;
                layerUsage.push_back(std::move(entry));
            }

            // Get instance count
            ON_SimpleArray<const CRhinoInstanceObject*> refs;
            idef->GetReferences(refs);

            nlohmann::json block;
            block["name"] = WideToUtf8(idef->Name());
            block["objectCount"] = objArray.Count();
            block["instanceCount"] = refs.Count();
            block["layerCount"] = static_cast<int>(layerCounts.size());
            block["layers"] = std::move(layerUsage);
            blocks.push_back(std::move(block));
        }

        nlohmann::json result;
        result["blockCount"] = static_cast<int>(blocks.size());
        result["blocks"] = std::move(blocks);
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

} // namespace Handlers
} // namespace Rook
