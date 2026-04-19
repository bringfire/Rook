// ArrayHandler.cpp
//
// Phase 1 typed array routes. See plan:
//   rook_docs/2026-04-17-typed-route-phase1-plan.md
//
// Substrate: direct-sdk (native C++).
//   - Native owns: HTTP entry, schema validation, source pre-flight, transform
//     loops, rollback-on-failure cleanup, and mutation response envelopes.
//   - Managed owns nothing here: array operations are direct ON_Xform loops
//     plus CRhinoDoc::TransformObject(..., bCopy=true), so bridge reuse would
//     add complexity without adding capability.
//
// Atomicity contract:
//   - One UndoScope per request groups the operation into a single undo record.
//   - UndoScope is NOT transactional rollback. On mid-loop failure the handler
//     explicitly deletes any copies created earlier in the request, then throws
//     operation_failed.
//
// Count semantics:
//   - total-including-source. count=5 means "leave the source in place and
//     create 4 new copies".
//
// Rectangular basis contract:
//   - The active view's CPlane is captured once on the UI thread at dispatch
//     time and echoed back as planeUsed in the success payload.

#include "stdafx.h"
#include "Handlers/ArrayHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/WriteResult.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <algorithm>
#include <atomic>
#include <cstdlib>
#include <string>
#include <vector>

namespace Rook {
namespace Handlers {

namespace {

struct StructuredError : public std::exception
{
    StructuredError(std::string codeIn, std::string messageIn)
        : code(std::move(codeIn)), message(std::move(messageIn)), whatCache(code + ": " + message)
    {
    }

    const char* what() const noexcept override
    {
        return whatCache.c_str();
    }

    std::string code;
    std::string message;

private:
    std::string whatCache;
};

struct LinearParams
{
    std::vector<ON_UUID> ids;
    ON_3dVector direction = ON_3dVector::ZeroVector;
    double spacing = 0.0;
    int count = 0;
};

struct RectangularParams
{
    std::vector<ON_UUID> ids;
    int xCount = 0;
    int yCount = 0;
    int zCount = 1;
    double xSpacing = 0.0;
    double ySpacing = 0.0;
    double zSpacing = 0.0;
};

struct PolarParams
{
    std::vector<ON_UUID> ids;
    ON_3dPoint center = ON_3dPoint::Origin;
    ON_3dVector axis = ON_3dVector::ZAxis;   // default world Z; explicit, never CPlane-derived
    int count = 0;
    double angle = 360.0;                     // total sweep, degrees; signed
    bool rotate = true;                       // false: orbit tight-bbox center, preserve orientation
};

std::atomic<int> g_debugFailCopyIndex{ 0 };

struct ScopedDebugArmReset
{
    ~ScopedDebugArmReset()
    {
        g_debugFailCopyIndex.store(0);
    }
};

nlohmann::json MakeErrorData(const std::string& errorCode, const std::string& errorMessage)
{
    return {
        {"errorCode", errorCode},
        {"errorMessage", errorMessage},
    };
}

void SendStructuredError(httplib::Response& res, const std::string& errorCode, const std::string& errorMessage)
{
    CRookServer::SendErrorData(res, MakeErrorData(errorCode, errorMessage));
}

nlohmann::json Point3dToJson(const ON_3dPoint& pt)
{
    return nlohmann::json::array({ RoundTo(pt.x, 4), RoundTo(pt.y, 4), RoundTo(pt.z, 4) });
}

nlohmann::json Vector3dToJson(const ON_3dVector& v)
{
    return nlohmann::json::array({ RoundTo(v.x, 4), RoundTo(v.y, 4), RoundTo(v.z, 4) });
}

bool DebugRoutesEnabledOrRefuse(httplib::Response& res)
{
    const char* env = std::getenv("ROOK_ENABLE_DEBUG_ROUTES");
    if (env != nullptr && std::string(env) == "1")
        return true;

    res.status = 403;
    res.set_header("Content-Type", "application/json");
    res.body = R"({"success":false,"data":"Debug routes disabled. Set ROOK_ENABLE_DEBUG_ROUTES=1 in the Rhino process environment and restart Rhino to enable /array/_debug/* routes. These routes are test-only and have no stable contract."})";
    return false;
}

bool ShouldSyntheticFailCopyAttempt(int copyAttemptOrdinal)
{
    int expected = copyAttemptOrdinal;
    return g_debugFailCopyIndex.compare_exchange_strong(expected, 0);
}

void RollBackCreatedCopies(CRhinoDoc* pDoc, const std::vector<ON_UUID>& createdIds)
{
    for (const ON_UUID& id : createdIds)
    {
        const CRhinoObject* created = pDoc->LookupObject(id);
        if (created)
            pDoc->DeleteObject(CRhinoObjRef(created), true);
    }
}

bool TryParseRequiredIds(const nlohmann::json& body, std::vector<ON_UUID>& idsOut, httplib::Response& res)
{
    if (!body.contains("ids") || !body["ids"].is_array())
    {
        SendStructuredError(res, "invalid_input", "Missing or invalid 'ids' (expected array of UUID strings)");
        return false;
    }

    try
    {
        idsOut = ParseUuids(body, "ids");
    }
    catch (const std::invalid_argument& ex)
    {
        SendStructuredError(res, "invalid_input", ex.what());
        return false;
    }

    if (idsOut.empty())
    {
        SendStructuredError(res, "invalid_input", "'ids' must contain at least one UUID");
        return false;
    }

    return true;
}

bool TryParseExactVector3(const nlohmann::json& body, const char* key, ON_3dVector& out, httplib::Response& res)
{
    if (!body.contains(key))
    {
        SendStructuredError(res, "invalid_input", std::string("Missing required field: ") + key);
        return false;
    }

    const auto& value = body[key];
    if (!value.is_array() || value.size() != 3)
    {
        SendStructuredError(res, "invalid_input", std::string("Field '") + key + "' must be a 3-number array [x,y,z]");
        return false;
    }

    for (int i = 0; i < 3; ++i)
    {
        if (!value[i].is_number())
        {
            SendStructuredError(res, "invalid_input", std::string("Field '") + key + "' must be a 3-number array [x,y,z]");
            return false;
        }
    }

    out = ON_3dVector(value[0].get<double>(), value[1].get<double>(), value[2].get<double>());
    return true;
}

bool TryParseRequiredNumber(const nlohmann::json& body, const char* key, double& out, httplib::Response& res)
{
    if (!body.contains(key) || !body[key].is_number())
    {
        SendStructuredError(res, "invalid_input", std::string("Field '") + key + "' must be a number");
        return false;
    }

    out = body[key].get<double>();
    return true;
}

bool TryParseRequiredCountField(const nlohmann::json& body, const char* key, int& out, httplib::Response& res)
{
    if (!body.contains(key) || !body[key].is_number_integer())
    {
        SendStructuredError(res, "invalid_count", std::string("Field '") + key + "' must be an integer >= 1");
        return false;
    }

    out = body[key].get<int>();
    if (out < 1)
    {
        SendStructuredError(res, "invalid_count", std::string("Field '") + key + "' must be >= 1");
        return false;
    }

    return true;
}

bool TryParseOptionalCountField(const nlohmann::json& body, const char* key, int defaultValue, int& out, httplib::Response& res)
{
    if (!body.contains(key))
    {
        out = defaultValue;
        return true;
    }

    if (!body[key].is_number_integer())
    {
        SendStructuredError(res, "invalid_count", std::string("Field '") + key + "' must be an integer >= 1");
        return false;
    }

    out = body[key].get<int>();
    if (out < 1)
    {
        SendStructuredError(res, "invalid_count", std::string("Field '") + key + "' must be >= 1");
        return false;
    }

    return true;
}

bool TryParseLinearParams(const nlohmann::json& body, LinearParams& params, httplib::Response& res)
{
    if (!TryParseRequiredIds(body, params.ids, res)) return false;
    if (!TryParseExactVector3(body, "direction", params.direction, res)) return false;
    if (!TryParseRequiredNumber(body, "spacing", params.spacing, res)) return false;
    if (!TryParseRequiredCountField(body, "count", params.count, res)) return false;

    if (!(params.spacing > 0.0))
    {
        SendStructuredError(res, "invalid_spacing", "Field 'spacing' must be > 0");
        return false;
    }

    return true;
}

bool TryParsePolarParams(const nlohmann::json& body, PolarParams& params, httplib::Response& res)
{
    if (!TryParseRequiredIds(body, params.ids, res)) return false;

    {
        ON_3dVector centerVec;
        if (!TryParseExactVector3(body, "center", centerVec, res)) return false;
        params.center = ON_3dPoint(centerVec.x, centerVec.y, centerVec.z);
    }

    if (body.contains("axis"))
    {
        if (!TryParseExactVector3(body, "axis", params.axis, res)) return false;
    }
    // else: axis already defaulted to world Z in the struct

    if (!TryParseRequiredCountField(body, "count", params.count, res)) return false;

    if (body.contains("angle"))
    {
        if (!body["angle"].is_number())
        {
            SendStructuredError(res, "invalid_input", "Field 'angle' must be a number");
            return false;
        }
        params.angle = body["angle"].get<double>();
    }
    // else: angle already defaulted to 360.0 in the struct

    if (body.contains("rotate"))
    {
        if (!body["rotate"].is_boolean())
        {
            SendStructuredError(res, "invalid_input", "Field 'rotate' must be a boolean");
            return false;
        }
        params.rotate = body["rotate"].get<bool>();
    }

    return true;
}

bool TryParseRectangularParams(const nlohmann::json& body, RectangularParams& params, httplib::Response& res)
{
    if (!TryParseRequiredIds(body, params.ids, res)) return false;
    if (!TryParseRequiredCountField(body, "xCount", params.xCount, res)) return false;
    if (!TryParseRequiredCountField(body, "yCount", params.yCount, res)) return false;
    if (!TryParseOptionalCountField(body, "zCount", 1, params.zCount, res)) return false;
    if (!TryParseRequiredNumber(body, "xSpacing", params.xSpacing, res)) return false;
    if (!TryParseRequiredNumber(body, "ySpacing", params.ySpacing, res)) return false;

    if (params.xCount > 1 && !(params.xSpacing > 0.0))
    {
        SendStructuredError(res, "invalid_spacing", "Field 'xSpacing' must be > 0 when xCount > 1");
        return false;
    }
    if (params.yCount > 1 && !(params.ySpacing > 0.0))
    {
        SendStructuredError(res, "invalid_spacing", "Field 'ySpacing' must be > 0 when yCount > 1");
        return false;
    }

    if (params.zCount > 1)
    {
        if (!body.contains("zSpacing") || !body["zSpacing"].is_number())
        {
            SendStructuredError(res, "zspacing_required", "Field 'zSpacing' is required and must be > 0 when zCount > 1");
            return false;
        }

        params.zSpacing = body["zSpacing"].get<double>();
        if (!(params.zSpacing > 0.0))
        {
            SendStructuredError(res, "zspacing_required", "Field 'zSpacing' is required and must be > 0 when zCount > 1");
            return false;
        }
    }
    else if (body.contains("zSpacing"))
    {
        if (!body["zSpacing"].is_number())
        {
            SendStructuredError(res, "invalid_input", "Field 'zSpacing' must be a number");
            return false;
        }
        // zSpacing is echoed in the stable response shape even when zCount==1,
        // so preserve an explicitly supplied value instead of normalizing away.
        params.zSpacing = body["zSpacing"].get<double>();
    }

    return true;
}

std::vector<const CRhinoObject*> ResolveSourcesOrThrow(CRhinoDoc* pDoc, const std::vector<ON_UUID>& ids)
{
    std::vector<const CRhinoObject*> sources;
    sources.reserve(ids.size());

    for (const ON_UUID& id : ids)
    {
        const CRhinoObject* src = pDoc->LookupObject(id);
        if (!src)
            throw StructuredError("not_found", "Source object not found: " + UuidToString(id));
        sources.push_back(src);
    }

    return sources;
}

CRhinoObject* TransformCopyOrThrow(
    CRhinoDoc* pDoc,
    const CRhinoObject* source,
    const ON_Xform& xform,
    std::vector<ON_UUID>& createdIds,
    int& copyAttemptIndex)
{
    ++copyAttemptIndex;
    if (ShouldSyntheticFailCopyAttempt(copyAttemptIndex))
    {
        RollBackCreatedCopies(pDoc, createdIds);
        pDoc->Redraw();
        throw std::runtime_error("Synthetic array test failure at copy attempt " + std::to_string(copyAttemptIndex));
    }

    CRhinoObject* copy = pDoc->TransformObject(source, xform, true, false, false);
    if (!copy)
    {
        RollBackCreatedCopies(pDoc, createdIds);
        pDoc->Redraw();
        throw std::runtime_error("TransformObject returned null at copy attempt " + std::to_string(copyAttemptIndex));
    }

    createdIds.push_back(copy->Attributes().m_uuid);
    return copy;
}

nlohmann::json MakeLinearSuccessData(
    const LinearParams& params,
    const std::vector<ON_UUID>& createdIds)
{
    nlohmann::json idsJson = nlohmann::json::array();
    for (const ON_UUID& id : createdIds)
        idsJson.push_back(UuidToString(id));

    nlohmann::json sourceIdsJson = nlohmann::json::array();
    for (const ON_UUID& id : params.ids)
        sourceIdsJson.push_back(UuidToString(id));

    return {
        {"createdCount", static_cast<int>(createdIds.size())},
        {"sourceIds", sourceIdsJson},
        {"ids", idsJson},
        {"mode", "linear"},
        {"direction", Vector3dToJson(params.direction)},
        {"spacing", params.spacing},
        {"count", params.count},
    };
}

// Reference point for polar `rotate=false`. Prefers tight bounding-box center
// (representation-independent — see BlocksHandler.cpp:837 for the full
// rationale around NURBS Brep representation drift on AddBrepObject). Falls
// back to BoundingBox().Center() only when GetTightBoundingBox returns invalid.
ON_3dPoint GetPolarReferencePoint(const CRhinoObject* src)
{
    ON_BoundingBox tight;
    if (src->GetTightBoundingBox(tight) && tight.IsValid())
        return tight.Center();
    return src->BoundingBox().Center();
}

// Compose the polar transform for a single copy.
//   rotate=true:  pure rotation around (center, axis) by thetaRad.
//   rotate=false: orbit the source's reference point around (center, axis) but
//                 cancel the orientation change with a counter-rotation around
//                 the new position. Net effect is a translation (P_k - P_S)
//                 with no orientation change. Reference point is captured per
//                 source pre-loop and reused across all k for that source.
ON_Xform ComputePolarXform(double thetaRad, const ON_3dVector& axisUnit,
                           const ON_3dPoint& center, const ON_3dPoint& referencePoint,
                           bool rotate)
{
    ON_Xform rotation;
    rotation.Rotation(thetaRad, axisUnit, center);

    if (rotate)
        return rotation;

    const ON_3dPoint newPt = rotation * referencePoint;
    ON_Xform counterRotation;
    counterRotation.Rotation(-thetaRad, axisUnit, newPt);
    return counterRotation * rotation;
}

nlohmann::json MakePolarSuccessData(
    const PolarParams& params,
    const std::vector<ON_UUID>& createdIds)
{
    nlohmann::json idsJson = nlohmann::json::array();
    for (const ON_UUID& id : createdIds)
        idsJson.push_back(UuidToString(id));

    nlohmann::json sourceIdsJson = nlohmann::json::array();
    for (const ON_UUID& id : params.ids)
        sourceIdsJson.push_back(UuidToString(id));

    return {
        {"createdCount", static_cast<int>(createdIds.size())},
        {"sourceIds", sourceIdsJson},
        {"ids", idsJson},
        {"mode", "polar"},
        {"center", Point3dToJson(params.center)},
        {"axis", Vector3dToJson(params.axis)},
        {"count", params.count},
        {"angle", params.angle},
        {"rotate", params.rotate},
    };
}

nlohmann::json MakeRectangularSuccessData(
    const RectangularParams& params,
    const std::vector<ON_UUID>& createdIds,
    const ON_Plane& plane)
{
    nlohmann::json idsJson = nlohmann::json::array();
    for (const ON_UUID& id : createdIds)
        idsJson.push_back(UuidToString(id));

    nlohmann::json sourceIdsJson = nlohmann::json::array();
    for (const ON_UUID& id : params.ids)
        sourceIdsJson.push_back(UuidToString(id));

    return {
        {"createdCount", static_cast<int>(createdIds.size())},
        {"sourceIds", sourceIdsJson},
        {"ids", idsJson},
        {"mode", "rectangular"},
        {"xCount", params.xCount},
        {"yCount", params.yCount},
        {"zCount", params.zCount},
        {"xSpacing", params.xSpacing},
        {"ySpacing", params.ySpacing},
        // When zCount==1 and zSpacing was omitted, echo the canonical default
        // 0.0 so the response shape stays stable across rectangular calls.
        {"zSpacing", params.zSpacing},
        {"planeUsed", {
            {"origin", Point3dToJson(plane.origin)},
            {"xAxis", Vector3dToJson(plane.xaxis)},
            {"yAxis", Vector3dToJson(plane.yaxis)},
            {"zAxis", Vector3dToJson(plane.zaxis)},
        }},
    };
}

} // namespace

void HandleLinear(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    ScopedDebugArmReset debugArmReset;

    LinearParams params;
    if (!TryParseLinearParams(body, params, res))
        return;

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, params]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        if (params.direction.Length() < ON_ZERO_TOLERANCE)
            throw StructuredError("degenerate_direction", "Field 'direction' must be non-zero");

        ON_3dVector unitDirection = params.direction;
        if (!unitDirection.Unitize())
            throw StructuredError("degenerate_direction", "Field 'direction' must be non-zero");

        std::vector<const CRhinoObject*> sources = ResolveSourcesOrThrow(pDoc, params.ids);
        std::vector<ON_UUID> createdIds;
        createdIds.reserve(static_cast<size_t>(sources.size()) * static_cast<size_t>(params.count - 1));

        int copyAttemptIndex = 0;
        {
            UndoScope undo(pDoc, L"Array Linear");

            for (const CRhinoObject* source : sources)
            {
                for (int k = 1; k < params.count; ++k)
                {
                    const ON_Xform xform = ON_Xform::TranslationTransformation(unitDirection * params.spacing * static_cast<double>(k));
                    TransformCopyOrThrow(pDoc, source, xform, createdIds, copyAttemptIndex);
                }
            }
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data = MakeLinearSuccessData(params, createdIds);
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
    catch (const StructuredError& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData(ex.code, ex.message));
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("invalid_input", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("operation_failed", ex.what()));
    }
}

void HandleRectangular(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    ScopedDebugArmReset debugArmReset;

    RectangularParams params;
    if (!TryParseRectangularParams(body, params, res))
        return;

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, params]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        CRhinoView* pView = RhinoApp().ActiveView();
        if (!pView)
            throw StructuredError("no_active_view", "No active view available to capture the construction plane");

        ON_Plane plane = pView->ActiveViewport().ConstructionPlane().m_plane;
        std::vector<const CRhinoObject*> sources = ResolveSourcesOrThrow(pDoc, params.ids);
        std::vector<ON_UUID> createdIds;
        createdIds.reserve(static_cast<size_t>(sources.size()) *
            static_cast<size_t>(params.xCount * params.yCount * params.zCount - 1));

        const ON_3dVector xStep = plane.xaxis * params.xSpacing;
        const ON_3dVector yStep = plane.yaxis * params.ySpacing;
        const ON_3dVector zStep = plane.zaxis * params.zSpacing;

        int copyAttemptIndex = 0;
        {
            UndoScope undo(pDoc, L"Array Rectangular");

            for (const CRhinoObject* source : sources)
            {
                for (int k = 0; k < params.zCount; ++k)
                {
                    for (int j = 0; j < params.yCount; ++j)
                    {
                        for (int i = 0; i < params.xCount; ++i)
                        {
                            if (i == 0 && j == 0 && k == 0)
                                continue;

                            const ON_3dVector delta =
                                xStep * static_cast<double>(i) +
                                yStep * static_cast<double>(j) +
                                zStep * static_cast<double>(k);
                            const ON_Xform xform = ON_Xform::TranslationTransformation(delta);
                            TransformCopyOrThrow(pDoc, source, xform, createdIds, copyAttemptIndex);
                        }
                    }
                }
            }
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data = MakeRectangularSuccessData(params, createdIds, plane);
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
    catch (const StructuredError& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData(ex.code, ex.message));
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("invalid_input", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("operation_failed", ex.what()));
    }
}

void HandlePolar(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    ScopedDebugArmReset debugArmReset;

    PolarParams params;
    if (!TryParsePolarParams(body, params, res))
        return;

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, params]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        // Source pre-flight ALWAYS runs, even at count==1 (so bogus uuids
        // surface as not_found rather than being silently masked by the
        // short-circuit). Plan: § /array/polar Resolved DR questions.
        std::vector<const CRhinoObject*> sources = ResolveSourcesOrThrow(pDoc, params.ids);

        // count==1 short-circuit: no copies, no rotation, axis value never
        // consumed. Bypasses both the copy loop and degenerate_axis /
        // angle_zero_with_count validation — those errors only matter when
        // an actual rotation is computed. Pinned in test (g) of the plan.
        if (params.count == 1)
        {
            WriteResult wr;
            wr.success = true;
            wr.data = MakePolarSuccessData(params, /*createdIds=*/{});
            return wr;
        }

        // Axis must be non-degenerate before unitization.
        if (params.axis.Length() < ON_ZERO_TOLERANCE)
            throw StructuredError("degenerate_axis", "Field 'axis' must be a non-zero vector");

        ON_3dVector axisUnit = params.axis;
        if (!axisUnit.Unitize())
            throw StructuredError("degenerate_axis", "Field 'axis' must be a non-zero vector");

        // angle == 0 with count > 1 would stack copies on the source position.
        // Reject rather than silently produce N overlapping duplicates.
        if (std::abs(params.angle) < 1e-9)
            throw StructuredError("angle_zero_with_count",
                "Field 'angle' must be non-zero when count > 1 (copies would stack on source)");

        // Signed full-circle predicate handles ±360 symmetrically. The signed
        // angle flows into both branches: +360/count and -360/count both avoid
        // the source position at k=count-1 (no collision); +180/(count-1) and
        // -180/(count-1) place the last copy at the signed angle. Plan:
        // § /array/polar Route/handler.
        const bool isFullCircle = std::abs(std::abs(params.angle) - 360.0) < 1e-9;
        const double step = isFullCircle
            ? (params.angle / static_cast<double>(params.count))
            : (params.angle / static_cast<double>(params.count - 1));

        // Capture per-source reference points pre-loop (used only when
        // rotate=false, but cheap to compute and keeps the loop branch-free).
        std::vector<ON_3dPoint> referencePoints;
        referencePoints.reserve(sources.size());
        for (const CRhinoObject* src : sources)
            referencePoints.push_back(GetPolarReferencePoint(src));

        std::vector<ON_UUID> createdIds;
        createdIds.reserve(static_cast<size_t>(sources.size()) * static_cast<size_t>(params.count - 1));

        int copyAttemptIndex = 0;
        {
            UndoScope undo(pDoc, L"Array Polar");

            for (size_t s = 0; s < sources.size(); ++s)
            {
                const CRhinoObject* source = sources[s];
                const ON_3dPoint& referencePoint = referencePoints[s];

                for (int k = 1; k < params.count; ++k)
                {
                    const double thetaRad = (step * static_cast<double>(k)) * (ON_PI / 180.0);
                    const ON_Xform xform = ComputePolarXform(
                        thetaRad, axisUnit, params.center, referencePoint, params.rotate);
                    TransformCopyOrThrow(pDoc, source, xform, createdIds, copyAttemptIndex);
                }
            }
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data = MakePolarSuccessData(params, createdIds);
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
    catch (const StructuredError& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData(ex.code, ex.message));
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("invalid_input", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("operation_failed", ex.what()));
    }
}

void HandleDebugFailNextCopy(const httplib::Request& req, httplib::Response& res)
{
    if (!DebugRoutesEnabledOrRefuse(res)) return;

    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    if (!body.contains("index") || !body["index"].is_number_integer())
    {
        SendStructuredError(res, "invalid_input", "Field 'index' must be an integer >= 1");
        return;
    }

    const int index = body["index"].get<int>();
    if (index < 1)
    {
        SendStructuredError(res, "invalid_input", "Field 'index' must be >= 1");
        return;
    }

    g_debugFailCopyIndex.store(index);

    nlohmann::json data = {
        {"armed", true},
        {"index", index},
    };
    CRookServer::SendSuccess(res, data);
}

} // namespace Handlers
} // namespace Rook
