// SurfaceHandler.cpp
//
// Phase 1 typed surface-creation routes. See plan:
//   rook_docs/2026-04-17-typed-route-phase1-plan.md
//
// Substrate: managed-bridge (reuse) with native error-envelope normalization.
//   - Native owns: HTTP entry, JSON parse, schema validation (required fields,
//     XOR exclusivity), response envelope shape, error-taxonomy mapping.
//   - Managed owns (via CreateGeometry callback at
//     src/Rook/Handlers/CreateHandler.cs): RhinoCommon factory invocation
//     (Brep.CreatePipe etc.), attribute application, document insertion,
//     ObjectSnapshot payload serialization.
//
// Error-envelope normalization: the managed CreateGeometry surface returns
// string-only errors ({success:false, data:"..."}). These routes rewrite
// managed string errors into structured {errorCode, errorMessage} form
// on the way back so the typed route ships the target contract from day
// one, rather than inheriting the reuse seam's legacy error shape.
//
// Strict-attributes convention (required for every new typed surface route):
// each handler MUST inject `_strictAttributes: true` into the request body
// before dispatching to InvokeManagedCreateWithBody. This opts the managed
// CreateGeometry path into Phase 1 contract behavior (unknown layer /
// unparseable color / wrong-type curveId → structured invalid_input;
// `visible` applied; plural creators route to their *Plural counterparts
// and return {objects: [...]} envelopes). Legacy /create callers that omit
// the flag keep pre-PR-1 silent-ignore behavior and singular-brep
// FirstOrDefault semantics — scope containment per the PR-1 Codex review.

#include "stdafx.h"
#include "Handlers/SurfaceHandler.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/ManagedCreateDispatch.h"
#include "RookServer.h"

#include <nlohmann/json.hpp>
#include <functional>
#include <string>

namespace Rook {
namespace Handlers {

// EmitNormalized + DispatchToManagedCreate were promoted from this
// file's anonymous namespace to Infrastructure/ManagedCreateDispatch.{h,cpp}
// in Phase 2 PR-4 (Rule 6 promotion-on-third-caller) when
// HandleCurveBoolean joined HandleBlendCurves + every HandleX here as the
// third caller. Calls within this file qualify through
// `Rook::Infrastructure::DispatchToManagedCreate`.
using Rook::Infrastructure::DispatchToManagedCreate;

// --- POST /surface/pipe -------------------------------------------------

void HandlePipe(const httplib::Request& req, httplib::Response& res)
{
    // documentSerialNumber is forwarded to managed in the body; native does
    // not need to resolve the doc here (the managed bridge marshals onto the
    // UI thread and calls ParseDocumentSerialNumber itself).
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    // Worker-thread schema validation (Rule 2).
    auto invalidInput = [&](const std::string& message) {
        nlohmann::json err = {
            {"errorCode", "invalid_input"},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // curveId — UUID format is checked here; object-existence + curve-ness
    // are deferred to the managed side (main-thread, doc-dependent).
    try { (void)ParseUuid(body, "curveId"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    const bool hasRadius = body.contains("radius");
    const bool hasStart = body.contains("startRadius");
    const bool hasEnd = body.contains("endRadius");

    // XOR: either `radius`, or both `startRadius` AND `endRadius`, not both
    // forms and not partial.
    if (hasRadius && (hasStart || hasEnd))
    {
        invalidInput("Provide either 'radius' OR both 'startRadius' and 'endRadius', not both forms");
        return;
    }
    if (!hasRadius && (hasStart != hasEnd))
    {
        invalidInput("Variable-radius pipe requires both 'startRadius' and 'endRadius'");
        return;
    }
    if (!hasRadius && !hasStart)
    {
        invalidInput("Missing radius: provide 'radius' OR both 'startRadius' and 'endRadius'");
        return;
    }

    auto requirePositiveNumber = [&](const nlohmann::json& el, const char* fieldName) -> bool {
        if (!el.is_number())
        {
            invalidInput(std::string("Field '") + fieldName + "' must be a number");
            return false;
        }
        const double v = el.get<double>();
        if (!(v > 0.0))
        {
            invalidInput(std::string("Field '") + fieldName + "' must be > 0");
            return false;
        }
        return true;
    };

    if (hasRadius && !requirePositiveNumber(body["radius"], "radius")) return;
    if (hasStart && !requirePositiveNumber(body["startRadius"], "startRadius")) return;
    if (hasEnd && !requirePositiveNumber(body["endRadius"], "endRadius")) return;

    if (body.contains("tolerance"))
    {
        if (!body["tolerance"].is_number() || body["tolerance"].get<double>() <= 0.0)
        {
            invalidInput("Field 'tolerance' must be a positive number");
            return;
        }
    }

    if (body.contains("cap") && !body["cap"].is_boolean())
    {
        invalidInput("Field 'cap' must be a boolean");
        return;
    }

    // Attribute bundle — syntactic checks (Rule 2 worker-thread). Document-
    // dependent checks (layer existence) happen managed-side, where bad
    // values now surface as structured invalid_input errors that pass
    // through the EmitNormalized path unchanged.
    if (body.contains("name") && !body["name"].is_string())
    {
        invalidInput("Field 'name' must be a string");
        return;
    }
    if (body.contains("layer"))
    {
        if (!body["layer"].is_string() || body["layer"].get<std::string>().empty())
        {
            invalidInput("Field 'layer' must be a non-empty string");
            return;
        }
    }
    if (body.contains("visible") && !body["visible"].is_boolean())
    {
        invalidInput("Field 'visible' must be a boolean");
        return;
    }
    if (body.contains("color"))
    {
        // Parse color natively; bad format → invalid_input before dispatch.
        try { (void)ParseColor(body, "color"); }
        catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    }

    // Build the managed CreateGeometry request: inject type:"PIPE" and
    // passthrough the validated params (including the attribute bundle).
    // `_strictAttributes` opts into the Phase 1 attribute-contract: unknown
    // layers and unparseable colors reject as structured invalid_input
    // rather than silently ignore. The managed-side gate keeps legacy
    // /create callers on the pre-PR-1 silent-ignore path, containing the
    // contract change to the typed surface routes.
    body["type"] = "PIPE";
    body["_strictAttributes"] = true;

    DispatchToManagedCreate(body.dump(), res);
}

// --- POST /surface/loft -------------------------------------------------
//
// Plural-contract route. Worker-thread validates curveIds (≥ 2, each UUID
// format), loftType enum, closed, convergence points, and the attribute
// bundle. Managed CreateLoftPlural (gated on _strictAttributes) handles
// curve resolution, factory invocation, atomic doc insertion, and
// {objects: [...]} envelope construction.

void HandleLoft(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    auto invalidInput = [&](const std::string& message, const char* code = "invalid_input") {
        nlohmann::json err = {
            {"errorCode", code},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // curveIds: required, array, min length 2, each element a valid UUID.
    if (!body.contains("curveIds") || !body["curveIds"].is_array())
    {
        invalidInput("Missing or invalid 'curveIds' (expected array of UUID strings)");
        return;
    }
    if (body["curveIds"].size() < 2)
    {
        invalidInput("Loft requires at least 2 curves", "insufficient_curves");
        return;
    }
    try { (void)ParseUuids(body, "curveIds"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    // loftType: optional string, case-insensitive enum check.
    if (body.contains("loftType"))
    {
        if (!body["loftType"].is_string())
        {
            invalidInput("Field 'loftType' must be a string", "invalid_loft_type");
            return;
        }
        std::string lt = body["loftType"].get<std::string>();
        static const char* kValid[] = {
            "Normal", "Loose", "Tight", "Straight", "Uniform", "Developable"
        };
        bool ok = false;
        for (const char* v : kValid)
        {
            if (IEquals(lt, v)) { ok = true; break; }
        }
        if (!ok)
        {
            invalidInput(
                "Invalid loftType: must be one of Normal/Loose/Tight/Straight/Uniform/Developable",
                "invalid_loft_type");
            return;
        }
    }

    // closed: optional boolean.
    if (body.contains("closed") && !body["closed"].is_boolean())
    {
        invalidInput("Field 'closed' must be a boolean");
        return;
    }
    const bool closed = body.value("closed", false);

    // Convergence points: optional [x,y,z] arrays.
    auto validatePoint = [&](const char* field) -> bool {
        if (!body.contains(field)) return true;
        const auto& el = body[field];
        if (!el.is_array() || el.size() != 3)
        {
            invalidInput(std::string("Field '") + field + "' must be [x,y,z]");
            return false;
        }
        for (const auto& c : el)
        {
            if (!c.is_number())
            {
                invalidInput(std::string("Field '") + field + "' coordinates must be numbers");
                return false;
            }
        }
        return true;
    };
    if (!validatePoint("startPoint")) return;
    if (!validatePoint("endPoint")) return;

    // closed + convergence conflict.
    if (closed && (body.contains("startPoint") || body.contains("endPoint")))
    {
        invalidInput(
            "Cannot combine closed=true with convergence points (startPoint/endPoint)",
            "convergence_point_conflict");
        return;
    }

    // Note: tolerance is intentionally not accepted on this route. The
    // RhinoCommon `Brep.CreateFromLoft(curves, start, end, type, closed)`
    // overload uses `doc.ModelAbsoluteTolerance` implicitly and exposes no
    // tolerance parameter. Honoring a user-supplied tolerance would require
    // switching to `CreateFromLoftRefit` (different semantics — adds
    // rebuild-point control) and is deferred to a future PR with an
    // explicit use case.

    // Attribute bundle — same syntactic checks as HandlePipe.
    if (body.contains("name") && !body["name"].is_string())
    {
        invalidInput("Field 'name' must be a string");
        return;
    }
    if (body.contains("layer"))
    {
        if (!body["layer"].is_string() || body["layer"].get<std::string>().empty())
        {
            invalidInput("Field 'layer' must be a non-empty string");
            return;
        }
    }
    if (body.contains("visible") && !body["visible"].is_boolean())
    {
        invalidInput("Field 'visible' must be a boolean");
        return;
    }
    if (body.contains("color"))
    {
        try { (void)ParseColor(body, "color"); }
        catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    }

    // Inject type + strict-attributes opt-in (see file header for convention).
    body["type"] = "LOFT";
    body["_strictAttributes"] = true;

    DispatchToManagedCreate(body.dump(), res);
}

// --- Shared validators for /surface/sweep* -------------------------------

namespace {

// Validate the attribute bundle (name/layer/color/visible) on the worker
// thread. Returns false and sends an invalid_input response on any schema
// violation; returns true on success (including when every field is absent).
bool ValidateAttributeBundle(
    const nlohmann::json& body,
    const std::function<void(const std::string&, const char*)>& invalidInput)
{
    if (body.contains("name") && !body["name"].is_string())
    {
        invalidInput("Field 'name' must be a string", "invalid_input");
        return false;
    }
    if (body.contains("layer"))
    {
        if (!body["layer"].is_string() || body["layer"].get<std::string>().empty())
        {
            invalidInput("Field 'layer' must be a non-empty string", "invalid_input");
            return false;
        }
    }
    if (body.contains("visible") && !body["visible"].is_boolean())
    {
        invalidInput("Field 'visible' must be a boolean", "invalid_input");
        return false;
    }
    if (body.contains("color"))
    {
        try { (void)ParseColor(body, "color"); }
        catch (const std::invalid_argument& ex)
        {
            invalidInput(ex.what(), "invalid_input");
            return false;
        }
    }
    return true;
}

} // namespace

// --- POST /surface/sweep1 -----------------------------------------------
//
// Plural-contract route. Worker-thread validates railId (UUID format),
// profileIds (≥ 1, each UUID format), style enum (Freeform | Roadlike),
// roadlikeUp presence rules (required iff Roadlike; rejected otherwise),
// closed type, and the attribute bundle. Managed CreateSweep1Plural (gated
// on _strictAttributes) resolves objects, configures SweepOneRail, and
// emits the plural {objects: [...]} envelope.

void HandleSweep1(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    auto invalidInput = [&](const std::string& message, const char* code = "invalid_input") {
        nlohmann::json err = {
            {"errorCode", code},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // railId: required, UUID format.
    try { (void)ParseUuid(body, "railId"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    // profileIds: required, array, min length 1, each UUID format.
    if (!body.contains("profileIds") || !body["profileIds"].is_array())
    {
        invalidInput("Missing or invalid 'profileIds' (expected array of UUID strings)");
        return;
    }
    if (body["profileIds"].size() == 0)
    {
        invalidInput("Sweep1 requires at least 1 profile curve", "no_profiles");
        return;
    }
    try { (void)ParseUuids(body, "profileIds"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    // closed: optional boolean.
    if (body.contains("closed") && !body["closed"].is_boolean())
    {
        invalidInput("Field 'closed' must be a boolean");
        return;
    }

    // style: optional enum (Freeform | Roadlike). AlignWithSurface deferred
    // to Phase 2 — surface-reference schema is unspecified in the plan.
    std::string styleStr = "Freeform";
    if (body.contains("style"))
    {
        if (!body["style"].is_string())
        {
            invalidInput("Field 'style' must be a string", "invalid_style");
            return;
        }
        styleStr = body["style"].get<std::string>();
        if (!(IEquals(styleStr, "Freeform") || IEquals(styleStr, "Roadlike")))
        {
            invalidInput(
                "Invalid style: must be 'Freeform' or 'Roadlike' (AlignWithSurface deferred to Phase 2)",
                "invalid_style");
            return;
        }
    }
    const bool isRoadlike = IEquals(styleStr, "Roadlike");

    // roadlikeUp: [x,y,z] direction vector. Required iff style == Roadlike.
    if (body.contains("roadlikeUp"))
    {
        if (!isRoadlike)
        {
            invalidInput(
                "'roadlikeUp' provided but style is not 'Roadlike'",
                "roadlike_up_without_style");
            return;
        }
        const auto& up = body["roadlikeUp"];
        if (!up.is_array() || up.size() != 3)
        {
            invalidInput("Field 'roadlikeUp' must be [x,y,z]");
            return;
        }
        double sumSq = 0.0;
        for (const auto& c : up)
        {
            if (!c.is_number())
            {
                invalidInput("Field 'roadlikeUp' coordinates must be numbers");
                return;
            }
            const double v = c.get<double>();
            sumSq += v * v;
        }
        if (sumSq <= 0.0)
        {
            invalidInput("Field 'roadlikeUp' must be non-zero");
            return;
        }
    }
    else if (isRoadlike)
    {
        invalidInput(
            "style='Roadlike' requires 'roadlikeUp' direction vector",
            "missing_roadlike_up");
        return;
    }

    if (!ValidateAttributeBundle(body, invalidInput)) return;

    body["type"] = "SWEEP1";
    body["_strictAttributes"] = true;

    DispatchToManagedCreate(body.dump(), res);
}

// --- POST /surface/sweep2 -----------------------------------------------
//
// Plural-contract route. Worker-thread validates rail1Id / rail2Id (UUID
// format, string inequality), profileIds (≥ 1, each UUID format), closed
// and maintainHeight types, and the attribute bundle. Managed
// CreateSweep2Plural handles object resolution, SweepTwoRail configuration,
// atomic insert, and the plural envelope.
//
// Empty PerformSweep result → operation_failed. The plan's
// `rails_disconnected` code is deferred until real geometric detection
// replaces the empty-result heuristic (Codex review 2026-04-17).

void HandleSweep2(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    auto invalidInput = [&](const std::string& message, const char* code = "invalid_input") {
        nlohmann::json err = {
            {"errorCode", code},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // rail1Id / rail2Id: required, UUID format, string-distinct.
    try { (void)ParseUuid(body, "rail1Id"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    try { (void)ParseUuid(body, "rail2Id"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    const std::string rail1Str = body["rail1Id"].get<std::string>();
    const std::string rail2Str = body["rail2Id"].get<std::string>();
    if (rail1Str == rail2Str)
    {
        invalidInput(
            "rail1Id and rail2Id refer to the same object (use Sweep1 instead)",
            "rails_coincident");
        return;
    }

    // profileIds: required, array, min length 1, each UUID format.
    if (!body.contains("profileIds") || !body["profileIds"].is_array())
    {
        invalidInput("Missing or invalid 'profileIds' (expected array of UUID strings)");
        return;
    }
    if (body["profileIds"].size() == 0)
    {
        invalidInput("Sweep2 requires at least 1 profile curve", "no_profiles");
        return;
    }
    try { (void)ParseUuids(body, "profileIds"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    if (body.contains("closed") && !body["closed"].is_boolean())
    {
        invalidInput("Field 'closed' must be a boolean");
        return;
    }
    if (body.contains("maintainHeight") && !body["maintainHeight"].is_boolean())
    {
        invalidInput("Field 'maintainHeight' must be a boolean");
        return;
    }

    if (!ValidateAttributeBundle(body, invalidInput)) return;

    body["type"] = "SWEEP2";
    body["_strictAttributes"] = true;

    DispatchToManagedCreate(body.dump(), res);
}

// --- POST /surface/revolve ----------------------------------------------
//
// Singular-contract route (bare ObjectSnapshot on success, same as Pipe).
// Worker-thread validates curveId UUID format, axisStart/axisEnd presence
// and shape, angle types, axis_degenerate (axisStart == axisEnd), and
// angle_invalid (startAngle == endAngle). Managed CreateRevolveStrict
// (gated on _strictAttributes) resolves the curve, builds the axis line,
// converts angles to radians, and invokes RevSurface.Create + ToBrep.
//
// The plan lists `curve_intersects_axis` as a route-specific error code.
// PR-4 ships this as a DEFERRED PLAN-CODE: detection requires geometric
// curve-line intersection checks (feasible via Intersection.CurveLine but
// tolerance-sensitive without a deterministic fixture). Factory failures
// — including the curve-crosses-axis case — classify as operation_failed
// in PR-4. The code itself remains in the plan's taxonomy; a future PR
// replaces the fallthrough with real geometric detection.
//
// tolerance deliberately omitted from the schema: RevSurface.ToBrep()
// takes no tolerance parameter, same API limitation as Loft's
// Brep.CreateFromLoft non-refit overload.

void HandleRevolve(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    auto invalidInput = [&](const std::string& message, const char* code = "invalid_input") {
        nlohmann::json err = {
            {"errorCode", code},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // curveId: required, UUID format.
    try { (void)ParseUuid(body, "curveId"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    // axisStart, axisEnd: required [x,y,z] arrays of numbers.
    auto parseAxisPoint = [&](const char* field, double out[3]) -> bool {
        if (!body.contains(field))
        {
            invalidInput(std::string("Missing required field: ") + field);
            return false;
        }
        const auto& el = body[field];
        if (!el.is_array() || el.size() != 3)
        {
            invalidInput(std::string("Field '") + field + "' must be [x,y,z]");
            return false;
        }
        for (int i = 0; i < 3; ++i)
        {
            if (!el[i].is_number())
            {
                invalidInput(std::string("Field '") + field + "' coordinates must be numbers");
                return false;
            }
            out[i] = el[i].get<double>();
        }
        return true;
    };
    double axisStart[3], axisEnd[3];
    if (!parseAxisPoint("axisStart", axisStart)) return;
    if (!parseAxisPoint("axisEnd", axisEnd)) return;

    // axis_degenerate: axisStart == axisEnd (coordinate-exact).
    if (axisStart[0] == axisEnd[0]
        && axisStart[1] == axisEnd[1]
        && axisStart[2] == axisEnd[2])
    {
        invalidInput(
            "axisStart and axisEnd are identical; axis has zero length",
            "axis_degenerate");
        return;
    }

    // startAngle, endAngle: optional numbers (degrees).
    double startAngle = 0.0;
    double endAngle = 360.0;
    if (body.contains("startAngle"))
    {
        if (!body["startAngle"].is_number())
        {
            invalidInput("Field 'startAngle' must be a number");
            return;
        }
        startAngle = body["startAngle"].get<double>();
    }
    if (body.contains("endAngle"))
    {
        if (!body["endAngle"].is_number())
        {
            invalidInput("Field 'endAngle' must be a number");
            return;
        }
        endAngle = body["endAngle"].get<double>();
    }

    // angle_invalid: startAngle == endAngle (empty sweep).
    if (startAngle == endAngle)
    {
        invalidInput(
            "startAngle and endAngle are identical; revolve sweep is empty",
            "angle_invalid");
        return;
    }

    if (!ValidateAttributeBundle(body, invalidInput)) return;

    body["type"] = "REVOLVE";
    body["_strictAttributes"] = true;

    DispatchToManagedCreate(body.dump(), res);
}

// --- POST /surface/edge -------------------------------------------------
//
// Phase 2 PR-1 worked example. Create a single brep from 2-4 boundary
// curves via `Brep.CreateEdgeSurface(curves)`. Singular-contract route
// (bare ObjectSnapshot on success).
//
// Worker-thread validation: `curveIds` required array of UUID strings,
// length in [2, 4]; each element parseable as UUID; attribute bundle
// syntactic checks. UUID-level rejection happens here; object-existence
// and is-a-curve validation happen managed-side (via ResolveCurvesStrict)
// with structured `invalid_input` / `not_found` errors that round-trip
// through EmitNormalized unchanged.
//
// The API-documented arity upper bound is 4; the Rhino `_-EdgeSrf`
// command UI has been empirically observed to accept 5+ (2026-04-20
// probe), but `Brep.CreateEdgeSurface` itself is bounded. The typed
// route enforces the API bound explicitly with route-specific
// `invalid_curve_count`.
//
// Factory permissiveness: `Brep.CreateEdgeSurface` empirically accepts
// pathological inputs (zero-length, coincident, disjoint, 3D non-planar)
// and still returns a valid brep. Per the Common Plan permissiveness
// amendment (`rook_docs/2026-04-17-typed-route-phase1-plan.md:257`, landed
// 2026-04-20), this route ships with a `test_factory_permissive_smoke`
// test rather than an operation_failed test.
//
// No tolerance parameter — `Brep.CreateEdgeSurface` does not expose one.

void HandleEdgeSrf(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    auto invalidInput = [&](const std::string& message, const char* code = "invalid_input") {
        nlohmann::json err = {
            {"errorCode", code},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // curveIds: required, array, length in [2, 4].
    if (!body.contains("curveIds") || !body["curveIds"].is_array())
    {
        invalidInput("Missing or invalid 'curveIds' (expected array of UUID strings)");
        return;
    }
    const size_t count = body["curveIds"].size();
    if (count < 2 || count > 4)
    {
        invalidInput(
            std::string("EdgeSrf requires 2-4 curves, got ") + std::to_string(count),
            "invalid_curve_count");
        return;
    }
    try { (void)ParseUuids(body, "curveIds"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    if (!ValidateAttributeBundle(body, invalidInput)) return;

    body["type"] = "EDGE_SRF";
    body["_strictAttributes"] = true;

    DispatchToManagedCreate(body.dump(), res);
}

// --- POST /surface/patch ------------------------------------------------
//
// Phase 2 PR-2. Brep.CreatePatch — fit a surface through
// curves/points/point-clouds, optionally seeded by a starting surface.
// Singular-contract route.
//
// Worker-thread validations (all rejections surface as structured errors):
//   - geometryIds: required array of UUIDs (min 1 element); each
//     UUID-format checked.
//   - startingSurfaceId: optional UUID string; object-existence + class
//     check deferred to managed ResolveSeedSurfaceStrict.
//   - uSpans/vSpans: optional positive integers (default 10). Factory
//     silently coerces zero, so reject here as invalid_spans.
//   - flexibility: optional positive number (default 1.0). Factory
//     silently coerces negatives, so reject here as invalid_flexibility.
//   - surfacePull: optional number (default 1.0). Type-check only —
//     factory accepts any real without observable coercion (2026-04-20
//     probe: values 0, -1, 100, 1e-10 all produced identical output).
//   - tolerance: optional positive number (default doc.ModelAbsoluteTolerance).
//     Factory silently accepts zero but produces ~50% larger surfaces;
//     reject here as invalid_input (matches Pipe's tolerance rule).
//   - Dependency rule: flexibility / surfacePull require startingSurfaceId.
//     Rejected with invalid_input — factory silently inert in the no-seed
//     path, so the route rejects to keep the user model honest.
//   - Attribute bundle (name/layer/color/visible): syntactic checks.
//
// Managed-side validations delegated to CreateHandler.CreatePatch:
//   - geometryIds object existence; accepted geometry classes are
//     Curve / Point / PointCloud (factory accepts more; route pre-filters
//     for contract clarity).
//   - startingSurfaceId accepted classes: Surface or single-face Brep
//     (auto-extracts UnderlyingSurface; rejects multi-face Brep and
//     non-Surface/non-Brep inputs as invalid_seed_class).
//
// Real Rhino-side failure case: single-point-only input empirically
// returns null (2026-04-20 probe). Satisfies Common Plan amendment at
// rook_docs/2026-04-17-typed-route-phase1-plan.md:257 — no
// test_factory_permissive_smoke needed.

void HandlePatch(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    auto invalidInput = [&](const std::string& message, const char* code = "invalid_input") {
        nlohmann::json err = {
            {"errorCode", code},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // geometryIds: required, array, min 1 element, UUID format per element.
    if (!body.contains("geometryIds") || !body["geometryIds"].is_array())
    {
        invalidInput("Missing or invalid 'geometryIds' (expected array of UUID strings)");
        return;
    }
    if (body["geometryIds"].size() < 1)
    {
        invalidInput("Patch requires at least 1 input geometry");
        return;
    }
    try { (void)ParseUuids(body, "geometryIds"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    // startingSurfaceId: optional, UUID format if present.
    const bool hasSeed = body.contains("startingSurfaceId");
    if (hasSeed)
    {
        if (!body["startingSurfaceId"].is_string()
            || body["startingSurfaceId"].get<std::string>().empty())
        {
            invalidInput("Field 'startingSurfaceId' must be a non-empty UUID string");
            return;
        }
        try { (void)ParseUuid(body, "startingSurfaceId"); }
        catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    }

    // uSpans / vSpans: optional positive integers.
    auto requirePositiveInt = [&](const char* fieldName) -> bool {
        if (!body.contains(fieldName)) return true;
        const auto& el = body[fieldName];
        if (!el.is_number_integer())
        {
            invalidInput(
                std::string("Field '") + fieldName + "' must be a positive integer",
                "invalid_spans");
            return false;
        }
        if (el.get<int>() <= 0)
        {
            invalidInput(
                std::string("Field '") + fieldName + "' must be > 0",
                "invalid_spans");
            return false;
        }
        return true;
    };
    if (!requirePositiveInt("uSpans")) return;
    if (!requirePositiveInt("vSpans")) return;

    // flexibility: optional positive number.
    if (body.contains("flexibility"))
    {
        const auto& el = body["flexibility"];
        if (!el.is_number())
        {
            invalidInput("Field 'flexibility' must be a number", "invalid_flexibility");
            return;
        }
        if (el.get<double>() <= 0.0)
        {
            invalidInput("Field 'flexibility' must be > 0", "invalid_flexibility");
            return;
        }
    }

    // surfacePull: optional number. Type-check only.
    if (body.contains("surfacePull") && !body["surfacePull"].is_number())
    {
        invalidInput("Field 'surfacePull' must be a number");
        return;
    }

    // tolerance: optional positive number.
    if (body.contains("tolerance"))
    {
        const auto& el = body["tolerance"];
        if (!el.is_number())
        {
            invalidInput("Field 'tolerance' must be a number");
            return;
        }
        if (el.get<double>() <= 0.0)
        {
            invalidInput("Field 'tolerance' must be > 0");
            return;
        }
    }

    // Dependency rule: flexibility / surfacePull require startingSurfaceId.
    if (!hasSeed)
    {
        if (body.contains("flexibility"))
        {
            invalidInput(
                "'flexibility' requires 'startingSurfaceId' (has no effect on the no-seed code path)");
            return;
        }
        if (body.contains("surfacePull"))
        {
            invalidInput(
                "'surfacePull' requires 'startingSurfaceId' (has no effect on the no-seed code path)");
            return;
        }
    }

    if (!ValidateAttributeBundle(body, invalidInput)) return;

    body["type"] = "PATCH";
    body["_strictAttributes"] = true;

    DispatchToManagedCreate(body.dump(), res);
}

// --- POST /surface/network ----------------------------------------------
//
// Phase 2 PR-3. NurbsSurface.CreateNetworkSurface — fit a NURBS surface
// through a network of curves, either auto-detected from a single list
// (curveIds) or explicit U/V (uCurveIds + vCurveIds). Singular-contract;
// managed wraps the result via Brep.CreateFromSurface for response-shape
// parity.
//
// Worker-thread validations (all rejections surface as structured errors):
//   INPUT FORM (XOR — exactly one must be present):
//     - both `curveIds` and (`uCurveIds` or `vCurveIds`) present
//       -> input_form_conflict
//     - explicit side: one of `uCurveIds` / `vCurveIds` present without
//       the other -> input_form_incomplete
//     - explicit side: either or both arrays empty -> input_form_incomplete
//       (empty array is the "missing for XOR" signal)
//     - neither form present -> invalid_input
//     - `curveIds` present but non-array or size < 2 -> invalid_input
//     - UUIDs malformed on any input array -> invalid_input
//   CONTINUITY:
//     - present but not integer in {0, 1, 2} -> invalid_continuity
//     - (factory silently coerces out-of-range values; probe 2026-04-20
//       showed 1/2/3/-1 all produce identical output — worker rejection
//       is load-bearing for contract clarity)
//   TOLERANCES (all three):
//     - present but non-number or <= 0 -> invalid_input
//     - (factory silently accepts zero/negative tolerances; probe showed
//       all-zero tolerances still produce non-null surface)
//   ATTRIBUTE BUNDLE: syntactic checks per ValidateAttributeBundle.
//
// Managed-side validations delegated to CreateHandler.CreateNetworkSrf:
//   - object existence + curve-class for all curve IDs (via ResolveCurvesStrict)
//   - factory-null OR non-zero `out error` -> operation_failed with
//     diagnostic message including the raw error code
//   - Brep.CreateFromSurface wrap-failure -> operation_failed
//
// Real Rhino-side failure cases (empirically verified 2026-04-20):
// parallel curves without crossing, single curve (worker catches first),
// disjoint far-apart curves — all return null with error=1. No
// test_factory_permissive_smoke needed; stable operation_failed paths
// satisfy the Common Plan amendment at
// rook_docs/2026-04-17-typed-route-phase1-plan.md:257.

void HandleNetworkSrf(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    auto invalidInput = [&](const std::string& message, const char* code = "invalid_input") {
        nlohmann::json err = {
            {"errorCode", code},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // --- Input-form XOR detection ---------------------------------------
    const bool hasCurveIds = body.contains("curveIds");
    const bool hasU = body.contains("uCurveIds");
    const bool hasV = body.contains("vCurveIds");
    const bool hasAnyExplicit = hasU || hasV;

    // Both forms present -> input_form_conflict
    if (hasCurveIds && hasAnyExplicit)
    {
        invalidInput(
            "Provide either 'curveIds' OR both 'uCurveIds' and 'vCurveIds', not both forms",
            "input_form_conflict");
        return;
    }

    // Neither form present -> invalid_input
    if (!hasCurveIds && !hasAnyExplicit)
    {
        invalidInput("must provide 'curveIds' or both 'uCurveIds' and 'vCurveIds'");
        return;
    }

    // Explicit side: both must be present and both must be non-empty.
    if (hasAnyExplicit)
    {
        if (!hasU || !hasV)
        {
            invalidInput(
                "explicit form requires both 'uCurveIds' and 'vCurveIds'",
                "input_form_incomplete");
            return;
        }
        if (!body["uCurveIds"].is_array() || !body["vCurveIds"].is_array())
        {
            invalidInput("'uCurveIds' and 'vCurveIds' must be arrays of UUID strings");
            return;
        }
        if (body["uCurveIds"].size() == 0 || body["vCurveIds"].size() == 0)
        {
            invalidInput(
                "'uCurveIds' and 'vCurveIds' must each contain at least one element",
                "input_form_incomplete");
            return;
        }
        try {
            (void)ParseUuids(body, "uCurveIds");
            (void)ParseUuids(body, "vCurveIds");
        }
        catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    }
    else
    {
        // Auto-detect form.
        if (!body["curveIds"].is_array())
        {
            invalidInput("'curveIds' must be an array of UUID strings");
            return;
        }
        if (body["curveIds"].size() < 2)
        {
            invalidInput("'curveIds' must contain at least 2 elements (auto-detect network)");
            return;
        }
        try { (void)ParseUuids(body, "curveIds"); }
        catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    }

    // --- continuity validation ------------------------------------------
    if (body.contains("continuity"))
    {
        const auto& el = body["continuity"];
        if (!el.is_number_integer())
        {
            invalidInput(
                "Field 'continuity' must be an integer (0=Position, 1=Tangency, 2=Curvature)",
                "invalid_continuity");
            return;
        }
        const int c = el.get<int>();
        if (c < 0 || c > 2)
        {
            invalidInput(
                std::string("Invalid continuity: ") + std::to_string(c)
                    + ". Must be 0 (Position), 1 (Tangency), or 2 (Curvature).",
                "invalid_continuity");
            return;
        }
    }

    // --- tolerance validation (all three) -------------------------------
    auto requirePositiveNumber = [&](const char* fieldName) -> bool {
        if (!body.contains(fieldName)) return true;
        const auto& el = body[fieldName];
        if (!el.is_number())
        {
            invalidInput(std::string("Field '") + fieldName + "' must be a number");
            return false;
        }
        if (el.get<double>() <= 0.0)
        {
            invalidInput(std::string("Field '") + fieldName + "' must be > 0");
            return false;
        }
        return true;
    };
    if (!requirePositiveNumber("edgeTolerance")) return;
    if (!requirePositiveNumber("interiorTolerance")) return;
    if (!requirePositiveNumber("angleTolerance")) return;

    if (!ValidateAttributeBundle(body, invalidInput)) return;

    body["type"] = "NETWORK_SRF";
    body["_strictAttributes"] = true;

    DispatchToManagedCreate(body.dump(), res);
}

} // namespace Handlers
} // namespace Rook
