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

#include <algorithm>
#include <vector>

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

// The `type` values POST /select accepts, with their ON::object_type bitmask.
// Single source for MapSelectTypeFilter and for the "accepted values" list in
// the error a caller gets for an unrecognized type, so the two cannot drift.
//
// The first block is the C# SelectionHandler mapping (several names are
// aliases: line/circle/arc/polyline all select curves, text selects
// annotations, block selects instance references). The second block adds the
// type names GET /objects prints, so a type read from rhino_objects can be
// passed to rhino_select. "Light" is deliberately absent: selection iterates
// without lights, so it could only ever select nothing.
struct SelectTypeEntry
{
    const char* name;
    unsigned int type;
};

static const std::vector<SelectTypeEntry>& SelectTypeEntries()
{
    static const std::vector<SelectTypeEntry> entries = {
        {"point",             ON::point_object},
        {"curve",             ON::curve_object},
        {"line",              ON::curve_object},
        {"circle",            ON::curve_object},
        {"arc",               ON::curve_object},
        {"polyline",          ON::curve_object},
        {"surface",           ON::surface_object},
        {"brep",              ON::brep_object},
        {"mesh",              ON::mesh_object},
        {"extrusion",         ON::extrusion_object},
        {"subd",              ON::subd_object},
        {"annotation",        ON::annotation_object},
        {"text",              ON::annotation_object},
        {"hatch",             ON::hatch_object},
        {"block",             ON::instance_reference},

        {"pointset",          ON::pointset_object},
        {"instancereference", ON::instance_reference},
        {"textdot",           ON::text_dot},
        {"clipplane",         ON::clipplane_object},
        {"detail",            ON::detail_object},
    };
    return entries;
}

// Map a type string to its ON::object_type bitmask, case-insensitively.
// Returns 0 for a name that is not in SelectTypeEntries. 0 is NOT "match
// all": HandleSelect rejects it before anything is selected. It used to be
// treated as match-all, so a misspelt or unsupported type selected every
// object in the document.
static unsigned int MapSelectTypeFilter(const std::string& typeStr)
{
    for (const auto& entry : SelectTypeEntries())
    {
        if (IEquals(typeStr, entry.name))
            return entry.type;
    }
    return 0;
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

    // An unrecognized `type` is an error, checked here before the dispatch so
    // that nothing is cleared or selected. MapSelectTypeFilter returns 0 for
    // it, and the type predicate used to read 0 as "match all".
    //
    // A `type` that is present but not a string (null, a number, an array,
    // ...) is rejected as well: the predicate below only runs for a string, so
    // such a request used to clear the selection, skip the type predicate and
    // report success. That includes null: a caller that sends `type` meant to
    // filter by it, and rhino_select_by_type requires it. Answering "0
    // selected" would tell that caller its filter matched nothing.
    if (body.contains("type") && !body["type"].is_string())
    {
        invalidInput("'type' must be a string");
        return;
    }
    if (body.contains("type") && body["type"].is_string())
    {
        const std::string typeStr = body["type"].get<std::string>();
        if (MapSelectTypeFilter(typeStr) == 0)
        {
            std::string names;
            nlohmann::json accepted = nlohmann::json::array();
            for (const auto& entry : SelectTypeEntries())
            {
                if (!names.empty()) names += ", ";
                names += entry.name;
                accepted.push_back(entry.name);
            }

            nlohmann::json err = {
                {"errorCode", "invalid_input"},
                {"errorMessage", "Unknown object type '" + typeStr +
                    "'. Accepted values (case-insensitive): " + names},
            };
            err["acceptedTypes"] = std::move(accepted);
            CRookServer::SendErrorData(res, err);
            return;
        }
    }

    // `includeSublayers` is an opt-in modifier of the `layer` predicate. The
    // default (false / absent) keeps Rhino's SelLayer meaning: only objects
    // directly on the named layer. Reject a malformed or orphaned flag rather
    // than silently selecting something other than what the caller meant.
    if (body.contains("includeSublayers"))
    {
        if (!body["includeSublayers"].is_boolean())
        {
            invalidInput("'includeSublayers' must be a boolean");
            return;
        }
        if (body["includeSublayers"].get<bool>() &&
            !(body.contains("layer") && body["layer"].is_string()))
        {
            invalidInput("'includeSublayers' requires 'layer'");
            return;
        }
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        // Selection is NOT in the undo system — no UndoScope needed.

        int selectedCount = 0;
        int deselectedCount = 0;
        int layersMatched = 0;

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

            // Default: the named layer only (objects on its sub-layers are NOT
            // selected, matching Rhino's SelLayer). `includeSublayers: true`
            // widens the match to every layer nested below it.
            const bool includeSublayers = body.value("includeSublayers", false);
            std::vector<int> layerIndices;
            if (includeSublayers)
                layerIndices = Rook::Infrastructure::CollectLayerWithDescendants(pDoc, layerIdx);
            else
                layerIndices.push_back(layerIdx);
            layersMatched = static_cast<int>(layerIndices.size());

            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (std::find(layerIndices.begin(), layerIndices.end(),
                              obj->Attributes().m_layer_index) != layerIndices.end())
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
            // Never 0 here: an unrecognized type was rejected before dispatch.
            // The guard keeps a 0 from ever meaning "every object" again.
            const unsigned int typeFilter = MapSelectTypeFilter(typeStr);
            if (typeFilter == 0)
                throw std::invalid_argument("Unknown object type '" + typeStr + "'");

            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                const bool matches =
                    (static_cast<unsigned int>(obj->ObjectType()) & typeFilter) != 0;
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
        // Reported only for an includeSublayers request: how many layers (the
        // named one plus its descendants) the layer predicate covered.
        if (body.value("includeSublayers", false))
            data["layersMatched"] = layersMatched;
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
