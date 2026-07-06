// DirectorPrepareHandler.cpp — Director v3 Slice 2 worker prepare.
//
// POST /director/prepare-take: explode declared actor-source block instances
// in the OPENED TAKE COPY with provenance recorded at creation time. The
// mapping key is (definition_object_index, definition_object_id) plus the
// occurrence path for nested instances — recorded DURING the explode, never
// matched post-hoc. Destructive by design; callers must pass
// expectedDocumentPath and the handler refuses any other active document.
// Spec: docs/superpowers/specs/2026-07-06-director-v3-snapshot-boundary-design.md

#include "stdafx.h"
#include "Handlers/DirectorPrepareHandler.h"
#include "Threading/MainThreadDispatcher.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/LayerHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "RookServer.h"
#include <cctype>
#include <set>
#include <string>
#include <vector>

namespace Rook {
namespace Handlers {

namespace {

constexpr int kMaxNestingDepth = 8;

// Must stay in lockstep with BlocksHandler.cpp's GetObjectTypeName —
// scene_manifest.json "expected.type" strings are produced there and
// compared for equality by director_worker_prepare.py.
std::string MemberTypeName(const CRhinoObject* obj)
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

// Same type coverage as BlocksHandler.cpp's AddGeometryToDoc. Unsupported
// geometry returns nullptr and the caller records a typed skip reason —
// never a silent continue.
const CRhinoObject* AddPreparedGeometry(CRhinoDoc* pDoc,
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

std::string NormalizePathForCompare(std::string s)
{
    for (char& c : s)
    {
        if (c == '\\') c = '/';
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return s;
}

void AddSkip(nlohmann::json& skipped, const std::string& path,
             const std::string& defObjId, const std::string& reason)
{
    skipped.push_back({{"occurrencePath", path},
                       {"definitionObjectId", defObjId},
                       {"reason", reason}});
}

// Recursively explode one definition object into top-level document objects.
// `accumXform` maps the object's local (definition) space to world space.
// `path` is the occurrence path of definition-object indices from the
// top-level member down ("3", "3/0", "3/0/2"). `visitedDefs` guards cycles
// per recursion branch (same pattern as BuildNestedHierarchy).
void ExplodeDefinitionObject(CRhinoDoc* pDoc, const CRhinoObject* defObj,
    const ON_Xform& accumXform, const std::string& path,
    std::set<int>& visitedDefs, int depth,
    nlohmann::json& created, nlohmann::json& skipped)
{
    if (!defObj || !defObj->Geometry())
    {
        AddSkip(skipped, path,
                defObj ? UuidToString(defObj->Attributes().m_uuid) : "",
                "null_definition_object");
        return;
    }
    const std::string defObjId = UuidToString(defObj->Attributes().m_uuid);

    if (const CRhinoInstanceObject* nestedInst = CRhinoInstanceObject::Cast(defObj))
    {
        if (depth >= kMaxNestingDepth)
        {
            AddSkip(skipped, path, defObjId, "nesting_too_deep");
            return;
        }
        const CRhinoInstanceDefinition* nestedDef = nestedInst->InstanceDefinition();
        if (!nestedDef)
        {
            AddSkip(skipped, path, defObjId, "nested_definition_not_found");
            return;
        }
        if (visitedDefs.count(nestedDef->Index()))
        {
            AddSkip(skipped, path, defObjId, "circular_nested_definition");
            return;
        }
        std::set<int> childVisited = visitedDefs;
        childVisited.insert(nestedDef->Index());
        const ON_Xform childXform = accumXform * nestedInst->InstanceXform();
        for (int j = 0; j < nestedDef->ObjectCount(); ++j)
        {
            ExplodeDefinitionObject(pDoc, nestedDef->Object(j), childXform,
                path + "/" + std::to_string(j), childVisited, depth + 1,
                created, skipped);
        }
        return;
    }

    ON_Geometry* dupGeom = defObj->Geometry()->Duplicate();
    if (!dupGeom)
    {
        AddSkip(skipped, path, defObjId, "geometry_duplicate_failed");
        return;
    }
    dupGeom->Transform(accumXform);

    ON_3dmObjectAttributes attrs = defObj->Attributes();
    attrs.m_uuid = ON_nil_uuid;  // fresh UUID mandate (spec Decision 2)
    const CRhinoObject* newObj = AddPreparedGeometry(pDoc, dupGeom, &attrs);
    if (!newObj)
    {
        const ON_ClassId* classId = defObj->Geometry()->ClassId();
        const std::string cls = classId ? classId->ClassName() : "unknown";
        AddSkip(skipped, path, defObjId, "unsupported_geometry_type:" + cls);
        delete dupGeom;
        return;
    }
    delete dupGeom;

    created.push_back({{"occurrencePath", path},
                       {"definitionObjectId", defObjId},
                       {"createdObjectId", UuidToString(newObj->Attributes().m_uuid)},
                       {"type", MemberTypeName(newObj)}});
}

} // anonymous namespace

void HandleDirectorPrepareTake(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("expectedDocumentPath") || !body["expectedDocumentPath"].is_string()
        || body["expectedDocumentPath"].get<std::string>().empty())
    {
        CRookServer::SendError(res, "expectedDocumentPath is required");
        return;
    }
    const std::string expectedPath = body["expectedDocumentPath"].get<std::string>();

    if (!body.contains("actorSets") || !body["actorSets"].is_array()
        || body["actorSets"].empty())
    {
        CRookServer::SendError(res, "actorSets must be a non-empty array");
        return;
    }

    struct ActorSetRequest { std::string actorSetId; ON_UUID instanceId; };
    std::vector<ActorSetRequest> actorSets;
    for (const auto& entry : body["actorSets"])
    {
        if (!entry.is_object() || !entry.contains("actorSetId")
            || !entry["actorSetId"].is_string())
        {
            CRookServer::SendError(res, "actorSets entries need actorSetId");
            return;
        }
        ActorSetRequest asr;
        asr.actorSetId = entry["actorSetId"].get<std::string>();
        try { asr.instanceId = ParseUuid(entry, "instanceId"); }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendError(res, ex.what());
            return;
        }
        actorSets.push_back(std::move(asr));
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, expectedPath, actorSets]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        // Braces half of the safety contract: never explode in anything but
        // the take copy the caller thinks is open (Python holds the belt).
        ON_wString docPathW = pDoc->GetPathName();
        const std::string docPath = WideToUtf8(docPathW);
        if (NormalizePathForCompare(docPath) != NormalizePathForCompare(expectedPath))
        {
            WriteResult wr;
            wr.success = false;
            wr.data["reason"] = "wrong_document";
            wr.data["documentPath"] = docPath;
            wr.data["expectedDocumentPath"] = expectedPath;
            return wr;
        }

        UndoScope undo(pDoc, L"Director prepare take");

        nlohmann::json actorSetsJson = nlohmann::json::array();
        for (const auto& asr : actorSets)
        {
            const CRhinoObject* obj = pDoc->LookupObject(asr.instanceId);
            if (!obj)
                throw std::invalid_argument(
                    "actor set '" + asr.actorSetId + "': instance not found");
            const CRhinoInstanceObject* pInstObj = CRhinoInstanceObject::Cast(obj);
            if (!pInstObj)
                throw std::invalid_argument(
                    "actor set '" + asr.actorSetId + "': object is not a block instance");
            const CRhinoInstanceDefinition* pDef = pInstObj->InstanceDefinition();
            if (!pDef)
                throw std::runtime_error(
                    "actor set '" + asr.actorSetId + "': could not resolve instance definition");

            const ON_Xform instXform = pInstObj->InstanceXform();
            nlohmann::json members = nlohmann::json::array();

            for (int i = 0; i < pDef->ObjectCount(); ++i)
            {
                const CRhinoObject* defObj = pDef->Object(i);
                nlohmann::json member;
                member["index"] = i;
                nlohmann::json created = nlohmann::json::array();
                nlohmann::json skipped = nlohmann::json::array();

                if (!defObj || !defObj->Geometry())
                {
                    // Not a manifest member (objects-detailed skips these too);
                    // reported so nothing is ever silently dropped.
                    member["definitionObjectId"] =
                        defObj ? UuidToString(defObj->Attributes().m_uuid) : "";
                    AddSkip(skipped, std::to_string(i),
                            member["definitionObjectId"].get<std::string>(),
                            "null_definition_object");
                    member["created"] = created;
                    member["skipped"] = skipped;
                    members.push_back(std::move(member));
                    continue;
                }

                const ON_3dmObjectAttributes& defAttrs = defObj->Attributes();
                member["definitionObjectId"] = UuidToString(defAttrs.m_uuid);
                member["type"] = MemberTypeName(defObj);
                // Shared helper lives in Rook::Infrastructure — this handler
                // is in Rook::Handlers, so it MUST be qualified (BlocksHandler
                // only calls it unqualified via its own file-local static).
                // Same wire format either way: GetLayerPathName -> UTF-8.
                member["layer"] = Infrastructure::GetLayerFullPath(pDoc, defAttrs.m_layer_index);
                member["name"] = WideToUtf8(defAttrs.m_name);

                // Definition-space tight bbox — the identical call
                // /block/objects-detailed used for the manifest evidence.
                ON_BoundingBox bbox;
                const bool tight = defObj->GetTightBoundingBox(bbox) && bbox.IsValid();
                if (tight)
                {
                    member["defBbox"]["min"] = { bbox.Min().x, bbox.Min().y, bbox.Min().z };
                    member["defBbox"]["max"] = { bbox.Max().x, bbox.Max().y, bbox.Max().z };
                    member["bboxMethod"] = "tight_object";
                }
                else
                {
                    ON_BoundingBox loose = defObj->BoundingBox();
                    if (loose.IsValid())
                    {
                        member["defBbox"]["min"] = { loose.Min().x, loose.Min().y, loose.Min().z };
                        member["defBbox"]["max"] = { loose.Max().x, loose.Max().y, loose.Max().z };
                        member["bboxMethod"] = "loose_fallback";
                    }
                    else
                    {
                        member["bboxMethod"] = "unavailable";
                    }
                }

                // Fresh visited set per top-level member: the same nested
                // definition appearing under two sibling members is legal;
                // cycles only matter within one recursion chain.
                std::set<int> visited;
                visited.insert(pDef->Index());
                ExplodeDefinitionObject(pDoc, defObj, instXform,
                    std::to_string(i), visited, 0, created, skipped);

                member["created"] = std::move(created);
                member["skipped"] = std::move(skipped);
                members.push_back(std::move(member));
            }

            // Destructive removal of the source occurrence — legal only
            // because this is the disposable copy (path-gated above).
            const bool deleted = pDoc->DeleteObject(
                CRhinoObjRef(pDoc->RuntimeSerialNumber(), asr.instanceId));
            if (!deleted)
                throw std::runtime_error(
                    "actor set '" + asr.actorSetId + "': failed to delete source instance");

            nlohmann::json setJson;
            setJson["actorSetId"] = asr.actorSetId;
            setJson["instanceId"] = UuidToString(asr.instanceId);
            setJson["definitionName"] = WideToUtf8(pDef->Name());
            setJson["instanceDeleted"] = true;
            setJson["members"] = std::move(members);
            actorSetsJson.push_back(std::move(setJson));
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["documentPath"] = docPath;
        wr.data["actorSets"] = std::move(actorSetsJson);
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

} // namespace Handlers
} // namespace Rook
