// SelectionHandler.cpp
//
// GET  /selection — Get currently selected objects with summary info
// POST /select    — Select/deselect objects by ID, layer, type, name, bbox, etc.
//
// Name-predicate contract (Phase 2 PR-0):
//   `name`        — exact attribute-name match, case-insensitive (matches
//                   the wildcard path's `towlower()` semantics so a caller
//                   migrating from `namePattern: "Alpha"` to `name: "alpha"`
//                   still matches the same objects).
//   `namePattern` — wildcard (* and ?) attribute-name match, case-insensitive.
//   Mixed `name` + `namePattern` in one request → invalid_input (structured error).
//
// Bbox-predicate contract (Phase 2 PR-0 additive):
//   `bbox: {min: [x,y,z], max: [x,y,z]}` — nested (router/BlocksHandler shape)
//   `bboxMin`, `bboxMax` (flat arrays)    — legacy shape, preserved for back-compat
//   Flat takes precedence over nested if both are present (stable callers keep
//   observing flat semantics). A malformed nested `bbox` (non-object, missing
//   min/max, non-array min/max, length < 3, non-numeric entries) emits
//   invalid_input rather than silently ignoring the filter — parity with the
//   legacy flat path, which throws via ParsePoint3d on bad input. Deprecation
//   of the flat form is deferred to a post-soak PR.

#include "stdafx.h"
#include "Handlers/SelectionHandler.h"
#include "Infrastructure/LayerHelpers.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/Snapshots.h"
#include "Models/DocumentHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

// Map type string to ON::object_type for selection filtering.
// Matches the C# SelectionHandler type mapping.
static unsigned int MapSelectTypeFilter(const std::string& typeStr)
{
    if (IEquals(typeStr, "point"))       return ON::point_object;
    if (IEquals(typeStr, "curve"))       return ON::curve_object;
    if (IEquals(typeStr, "line"))        return ON::curve_object;
    if (IEquals(typeStr, "circle"))      return ON::curve_object;
    if (IEquals(typeStr, "arc"))         return ON::curve_object;
    if (IEquals(typeStr, "polyline"))    return ON::curve_object;
    if (IEquals(typeStr, "surface"))     return ON::surface_object;
    if (IEquals(typeStr, "brep"))        return ON::brep_object;
    if (IEquals(typeStr, "mesh"))        return ON::mesh_object;
    if (IEquals(typeStr, "extrusion"))   return ON::extrusion_object;
    if (IEquals(typeStr, "subd"))        return ON::subd_object;
    if (IEquals(typeStr, "annotation")) return ON::annotation_object;
    if (IEquals(typeStr, "text"))        return ON::annotation_object;
    if (IEquals(typeStr, "hatch"))       return ON::hatch_object;
    if (IEquals(typeStr, "block"))       return ON::instance_reference;
    return 0;  // 0 = match all
}

// Simple wildcard matching with * and ? support.
static bool WildcardMatch(const wchar_t* pattern, const wchar_t* str)
{
    while (*pattern)
    {
        if (*pattern == L'*')
        {
            ++pattern;
            if (!*pattern) return true;
            while (*str)
            {
                if (WildcardMatch(pattern, str))
                    return true;
                ++str;
            }
            return false;
        }
        else if (*pattern == L'?' || towlower(*pattern) == towlower(*str))
        {
            ++pattern;
            ++str;
        }
        else
        {
            return false;
        }
    }
    return !*str;
}

// ─── GET /selection ─────────────────────────────────────────────────

void HandleGetSelection(const httplib::Request& req, httplib::Response& res)
{
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

    // Capture selected objects on main thread
    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> std::vector<ObjectSnapshot>
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        std::vector<ObjectSnapshot> selected;
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);

        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            if (!obj->IsSelected()) continue;
            auto snap = CaptureObjectSnapshot(obj, pDoc);

            // Block instance enrichment (selection only — not in GET /objects)
            if (obj->ObjectType() == ON::instance_reference)
            {
                const CRhinoInstanceObject* pInst = CRhinoInstanceObject::Cast(obj);
                if (pInst)
                {
                    const CRhinoInstanceDefinition* pDef = pInst->InstanceDefinition();
                    if (pDef)
                    {
                        snap.blockName = WideToUtf8(pDef->Name());
                        snap.blockDefinitionId = UuidToString(pDef->Id());
                    }
                }
            }

            selected.push_back(std::move(snap));
        }

        return selected;
    });

    try
    {
        auto selected = future.get();

        // Serialize on worker thread
        nlohmann::json objects = nlohmann::json::array();
        for (const auto& snap : selected)
            objects.push_back(Serializer::SerializeObject(snap));

        nlohmann::json data;
        data["count"] = static_cast<int>(selected.size());
        data["objects"] = std::move(objects);
        data["subObjectCount"] = 0;
        data["subObjects"] = nlohmann::json::array();

        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /select ───────────────────────────────────────────────────

void HandleSelect(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Structured-error helper for new PR-0 validation paths. Existing error
    // paths in this handler still use SendError (string) and are not rewritten
    // by PR-0 — Decision Record §6 drift cleanup, not this PR's scope.
    auto invalidInput = [&](const std::string& message) {
        nlohmann::json err = {
            {"errorCode", "invalid_input"},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // Phase 2 PR-0 additive-contract validation. `name` (exact match) and
    // `namePattern` (wildcard) are different matching strategies on the same
    // field; combining them in one request is caller confusion. Reject rather
    // than precedence-ordering them.
    if (body.contains("name") && body["name"].is_string() &&
        body.contains("namePattern") && body["namePattern"].is_string())
    {
        invalidInput("Provide either 'name' (exact match) or 'namePattern' (wildcard), not both");
        return;
    }

    // Worker-thread validation of nested `bbox` shape. If the caller sent
    // `bbox:{min,max}` (without the legacy flat form), require a well-formed
    // structure — do not silently drop the filter. The legacy flat form still
    // routes through ParsePoint3d inside the lambda and throws on bad input,
    // so parity is: both shapes surface malformed input rather than accepting
    // the request and filtering on nothing.
    if (!body.contains("bboxMin") && !body.contains("bboxMax") &&
        body.contains("bbox"))
    {
        const auto& bboxField = body["bbox"];
        if (!bboxField.is_object() ||
            !bboxField.contains("min") || !bboxField.contains("max") ||
            !bboxField["min"].is_array() || !bboxField["max"].is_array() ||
            bboxField["min"].size() < 3 || bboxField["max"].size() < 3)
        {
            invalidInput("'bbox' must be an object {min: [x,y,z], max: [x,y,z]}");
            return;
        }
        for (int i = 0; i < 3; ++i)
        {
            if (!bboxField["min"][i].is_number() ||
                !bboxField["max"][i].is_number())
            {
                invalidInput("'bbox.min' and 'bbox.max' entries must be numbers");
                return;
            }
        }
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        // Selection is NOT in the undo system — no UndoScope needed.

        int selectedCount = 0;
        int deselectedCount = 0;

        // Processing order matches C# SelectionHandler exactly.

        // 1. clear (default: true)
        bool clearFirst = body.value("clear", true);
        if (clearFirst)
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (obj->IsSelected())
                {
                    const_cast<CRhinoObject*>(obj)->Select(false);
                    ++deselectedCount;
                }
            }
        }

        // 2. deselectIds
        if (body.contains("deselectIds") && body["deselectIds"].is_array())
        {
            for (const auto& idVal : body["deselectIds"])
            {
                if (!idVal.is_string()) continue;
                ON_UUID uuid = ON_UuidFromString(idVal.get<std::string>().c_str());
                if (ON_UuidIsNil(uuid)) continue;

                const CRhinoObject* obj = pDoc->LookupObject(uuid);
                if (obj && obj->IsSelected())
                {
                    const_cast<CRhinoObject*>(obj)->Select(false);
                    ++deselectedCount;
                }
            }
        }

        // 3. ids
        if (body.contains("ids") && body["ids"].is_array())
        {
            for (const auto& idVal : body["ids"])
            {
                if (!idVal.is_string()) continue;
                ON_UUID uuid = ON_UuidFromString(idVal.get<std::string>().c_str());
                if (ON_UuidIsNil(uuid)) continue;

                const CRhinoObject* obj = pDoc->LookupObject(uuid);
                if (obj)
                {
                    const_cast<CRhinoObject*>(obj)->Select(true);
                    ++selectedCount;
                }
            }
        }

        // 4. layer
        if (body.contains("layer") && body["layer"].is_string())
        {
            std::string layerName = body["layer"].get<std::string>();
            const int layerIdx = Rook::Infrastructure::ResolveLayerRef(
                pDoc, layerName, "layer").index;
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (obj->Attributes().m_layer_index == layerIdx)
                {
                    const_cast<CRhinoObject*>(obj)->Select(true);
                    ++selectedCount;
                }
            }
        }

        // 5. type
        if (body.contains("type") && body["type"].is_string())
        {
            std::string typeStr = body["type"].get<std::string>();
            unsigned int typeFilter = MapSelectTypeFilter(typeStr);

            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                bool matches = (typeFilter == 0) ||
                    (static_cast<unsigned int>(obj->ObjectType()) & typeFilter);
                if (matches)
                {
                    const_cast<CRhinoObject*>(obj)->Select(true);
                    ++selectedCount;
                }
            }
        }

        // 6. namePattern (wildcard with * and ?)
        if (body.contains("namePattern") && body["namePattern"].is_string())
        {
            std::string pattern = body["namePattern"].get<std::string>();
            ON_wString wPattern = Utf8ToWide(pattern);

            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                ON_wString objName = obj->Attributes().m_name;
                if (objName.IsEmpty()) continue;

                if (WildcardMatch(static_cast<const wchar_t*>(wPattern),
                                  static_cast<const wchar_t*>(objName)))
                {
                    const_cast<CRhinoObject*>(obj)->Select(true);
                    ++selectedCount;
                }
            }
        }

        // 6b. name (exact match, case-insensitive). PR-0 additive compatibility:
        //     the router's select_objects RouteSpec advertises `name` but the
        //     handler previously only implemented `namePattern`. Comparison is
        //     case-insensitive to match the wildcard path's `towlower(...)`
        //     semantics at WildcardMatch — a caller migrating from
        //     `namePattern: "Alpha"` to `name: "alpha"` must still match the
        //     same objects. Mixed with `namePattern` was already rejected on
        //     the worker thread above.
        if (body.contains("name") && body["name"].is_string())
        {
            std::string nameExact = body["name"].get<std::string>();
            ON_wString wNameExact = Utf8ToWide(nameExact);

            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                ON_wString objName = obj->Attributes().m_name;
                if (objName.IsEmpty()) continue;

                if (objName.CompareNoCase(static_cast<const wchar_t*>(wNameExact)) == 0)
                {
                    const_cast<CRhinoObject*>(obj)->Select(true);
                    ++selectedCount;
                }
            }
        }

        // 7. bbox — accept either flat bboxMin/bboxMax OR nested bbox:{min,max}.
        //    PR-0 additive compatibility with the router RouteSpec + BlocksHandler
        //    /block/find-instances shape. Flat form preserved for back-compat;
        //    deprecation deferred to a post-soak PR.
        {
            bool hasBbox = false;
            ON_3dPoint bboxMin, bboxMax;

            if (body.contains("bboxMin") && body.contains("bboxMax"))
            {
                bboxMin = ParsePoint3d(body, "bboxMin");
                bboxMax = ParsePoint3d(body, "bboxMax");
                hasBbox = true;
            }
            else if (body.contains("bbox") && body["bbox"].is_object()
                     && body["bbox"].contains("min") && body["bbox"].contains("max")
                     && body["bbox"]["min"].is_array() && body["bbox"]["max"].is_array()
                     && body["bbox"]["min"].size() >= 3 && body["bbox"]["max"].size() >= 3)
            {
                const auto& minArr = body["bbox"]["min"];
                const auto& maxArr = body["bbox"]["max"];
                bboxMin = ON_3dPoint(
                    minArr[0].get<double>(),
                    minArr[1].get<double>(),
                    minArr[2].get<double>());
                bboxMax = ON_3dPoint(
                    maxArr[0].get<double>(),
                    maxArr[1].get<double>(),
                    maxArr[2].get<double>());
                hasBbox = true;
            }

            if (hasBbox)
            {
                ON_BoundingBox selBox(bboxMin, bboxMax);

                CRhinoObjectIterator it(*pDoc,
                    CRhinoObjectIterator::normal_or_locked_objects,
                    CRhinoObjectIterator::active_objects);
                for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
                {
                    ON_BoundingBox objBox = obj->BoundingBox();
                    if (objBox.IsValid())
                    {
                        // Select if object bbox is contained in selBox, or its center is.
                        // Matches C# behavior: selectionBox.Contains(objBox) || selectionBox.Contains(objBox.Center)
                        bool contained = selBox.Includes(objBox);
                        if (!contained)
                            contained = selBox.IsPointIn(objBox.Center());
                        if (contained)
                        {
                            const_cast<CRhinoObject*>(obj)->Select(true);
                            ++selectedCount;
                        }
                    }
                }
            }
        }

        // 8. all
        if (body.contains("all") && body["all"].is_boolean() && body["all"].get<bool>())
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                const_cast<CRhinoObject*>(obj)->Select(true);
                ++selectedCount;
            }
        }

        // 9. none
        if (body.contains("none") && body["none"].is_boolean() && body["none"].get<bool>())
        {
            selectedCount = 0;
            deselectedCount = 0;
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (obj->IsSelected())
                {
                    const_cast<CRhinoObject*>(obj)->Select(false);
                    ++deselectedCount;
                }
            }
        }

        // 10. invert
        if (body.contains("invert") && body["invert"].is_boolean() && body["invert"].get<bool>())
        {
            selectedCount = 0;
            deselectedCount = 0;
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (obj->IsSelected())
                {
                    const_cast<CRhinoObject*>(obj)->Select(false);
                    ++deselectedCount;
                }
                else
                {
                    const_cast<CRhinoObject*>(obj)->Select(true);
                    ++selectedCount;
                }
            }
        }

        pDoc->Redraw();

        nlohmann::json data;
        data["selectedCount"] = selectedCount;
        if (deselectedCount > 0)
            data["deselectedCount"] = deselectedCount;
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
