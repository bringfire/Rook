// AnnotationHandler.cpp
//
// Phase 2 typed annotation-creation routes. See plan:
//   rook_docs/2026-04-19-typed-route-phase2-plan.md
//
// Substrate: direct-sdk (native C++).
//   - Native owns: HTTP entry, JSON parse, schema validation, dimstyle
//     override construction (SetTextHeight / SetAnnotationFont /
//     SetAnnotationBold / SetAnnotationItalic / SetAnnotationFacename),
//     pDoc->CreateTextObject + pDoc->AddObject, strict attribute
//     application, response envelope.
//   - Managed owns nothing here.
//
// Substrate rationale (per gap-analysis 2026-04-19 decision, binding
// under Decision Record Rule 6):
//   (a) RookNative is the public HTTP surface; managed is internal
//       companion. Typed routes belong on the public substrate.
//   (b) Native already has higher-fidelity TEXT than managed (override
//       persistence at CreateHandler.cpp:558-563 not replicated on the
//       managed factory).
//   (c) Routing through managed would introduce a new bridge_unavailable
//       / 503 mode for operations that have no bridge dependency today.
//   (d) Avoids baking managed's strict-attrs bypass (managed's annotation
//       switch at CreateHandler.cs:93-121 returns before the attribute
//       block at :181) and LINEAR/ALIGNED collapse into the new contract.
//
// Strict-attrs convention: Phase 2 annotation routes enforce strict
// attribute application from day one — no _strictAttributes flag opt-in.
// Unknown layer / unparseable color / non-boolean visible → structured
// invalid_input. Legacy /create?type=TEXT remains on the lax
// ApplyCommonAttributes (CreateHandler.cpp:91-117) and is untouched by
// this PR.
//
// Factory-body policy: the TEXT factory body is copied near-verbatim
// from CreateHandler.cpp:514-576 rather than shared with the legacy
// caller. Premature helper extraction between a strict typed route and
// a legacy lax route would couple the two before there is a second typed
// caller to justify the seam (Codex 2026-04-19). A shared-factory
// consolidation PR is reasonable once a second annotation variant lands.
//
// Response-payload echo policy: typography fields (font, bold, italic,
// height) in the success payload are the EFFECTIVE applied values read
// from the created annotation via GetEffectiveDimensionStyle, NOT the
// request parameters. Font-characteristic failures fall back to the
// document default font; the response reflects the fallback, so callers
// can verify what was actually persisted without a follow-up GET
// /geometry read.

#include "stdafx.h"
#include "Handlers/AnnotationHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/LayerHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/WriteResult.h"
#include "Models/Snapshots.h"
#include "Models/DocumentHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <nlohmann/json.hpp>
#include <string>

namespace Rook {
namespace Handlers {

namespace {

// Strict attribute application for Phase 2 typed routes. Distinct from
// CreateHandler.cpp's ApplyCommonAttributes (:91-117), which silently
// ignores unparseable colors (catch(...) at :115) and does not handle
// `visible` at all. This variant:
//   - delegates layer resolution to ResolveLayerRef (already throws on
//     unknown / empty / ambiguous — LayerHelpers.cpp:77-107);
//   - lets ParseColor's throw propagate (no catch);
//   - validates and applies `visible` as a boolean (non-boolean throws).
// Callers rely on std::invalid_argument propagating to the top-level
// catch for mapping to structured invalid_input.
void ApplyCommonAttributesStrict(ON_3dmObjectAttributes& attrs,
                                  const nlohmann::json& body,
                                  CRhinoDoc* pDoc)
{
    if (body.contains("name"))
    {
        if (!body["name"].is_string())
            throw std::invalid_argument("Field 'name' must be a string");
        attrs.m_name = Utf8ToWide(body["name"].get<std::string>());
    }

    if (body.contains("layer"))
    {
        if (!body["layer"].is_string())
            throw std::invalid_argument("Field 'layer' must be a string");
        std::string layerName = body["layer"].get<std::string>();
        auto ref = Rook::Infrastructure::ResolveLayerRef(pDoc, layerName, "layer");
        attrs.m_layer_index = ref.index;
    }

    if (body.contains("color"))
    {
        ON_Color c = ParseColor(body, "color");
        attrs.m_color = c;
        attrs.SetColorSource(ON::color_from_object);
    }

    if (body.contains("visible"))
    {
        if (!body["visible"].is_boolean())
            throw std::invalid_argument("Field 'visible' must be a boolean");
        attrs.SetVisible(body["visible"].get<bool>());
    }
}

} // namespace

// --- POST /annotation/text ----------------------------------------------

void HandleText(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto invalidInput = [&](const std::string& message) {
        nlohmann::json err = {
            {"errorCode", "invalid_input"},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // Worker-thread schema validation (Rule 2).

    if (!body.contains("text") || !body["text"].is_string())
    {
        invalidInput("Missing required field: text");
        return;
    }
    if (body["text"].get<std::string>().empty())
    {
        invalidInput("'text' must be a non-empty string");
        return;
    }

    if (body.contains("height"))
    {
        if (!body["height"].is_number())
        {
            invalidInput("'height' must be a number");
            return;
        }
        if (!(body["height"].get<double>() > 0.0))
        {
            invalidInput("'height' must be > 0");
            return;
        }
    }

    if (body.contains("font") && !body["font"].is_string())
    {
        invalidInput("'font' must be a string");
        return;
    }

    if (body.contains("bold") && !body["bold"].is_boolean())
    {
        invalidInput("'bold' must be a boolean");
        return;
    }

    if (body.contains("italic") && !body["italic"].is_boolean())
    {
        invalidInput("'italic' must be a boolean");
        return;
    }

    if (body.contains("point"))
    {
        if (!body["point"].is_array() || body["point"].size() != 3)
        {
            invalidInput("'point' must be an array of exactly 3 numbers");
            return;
        }
        for (int i = 0; i < 3; ++i)
        {
            if (!body["point"][i].is_number())
            {
                invalidInput("'point' entries must be numbers");
                return;
            }
        }
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Create Text");

        // Apply strict attributes before constructing the annotation. Any
        // failure here (unknown layer, unparseable color, non-boolean
        // visible) throws std::invalid_argument, caught by the top-level
        // handler and mapped to structured invalid_input.
        ON_3dmObjectAttributes attrs;
        ApplyCommonAttributesStrict(attrs, body, pDoc);

        // --- Factory body (copied near-verbatim from
        // CreateHandler.cpp:514-576 per factory-body policy in file
        // header). The legacy caller at CreateHandler.cpp:664-665
        // remains wired to the original in-file factory for
        // legacy-compat; this copy is the canonical home for the
        // strict typed route. ---

        const std::string text = body["text"].get<std::string>();
        const ON_3dPoint point = ParsePoint3dOrDefault(body, "point", ON_3dPoint::Origin);
        const double height = body.value("height", 1.0);

        ON_Plane plane = ON_Plane::World_xy;
        plane.origin = point;

        const auto dimContext = pDoc->DimStyleContext();
        const ON_DimStyle parentDimStyle = dimContext.CurrentDimStyle();
        ON_DimStyle dimStyle = parentDimStyle;
        dimStyle.SetTextHeight(height);

        const std::string fontName = body.value("font", std::string("Arial"));
        const bool bold = body.value("bold", false);
        const bool italic = body.value("italic", false);

        ON_Font font;
        const bool fontApplied = font.SetFontCharacteristics(
            Utf8ToWide(fontName),
            bold,
            italic,
            false,
            false);
        if (!fontApplied)
        {
            // Match legacy behavior: fall back to document default when
            // the requested font is unavailable. The response payload
            // will echo the effective font (see below), so callers can
            // observe the fallback without a follow-up read.
            font = RhinoApp().AppSettings().DefaultFont();
        }
        dimStyle.SetFont(font);

        ON_Text textObject;
        const ON_wString wideText = Utf8ToWide(text);
        if (!textObject.Create(wideText, &dimStyle, plane))
            throw std::runtime_error("Failed to build text annotation");

        // Annotation-level override persistence. Passing the override
        // dimstyle into ON_Text::Create() alone is not enough for the
        // final object to retain height/font styling.
        textObject.SetTextHeight(&parentDimStyle, height);
        textObject.SetAnnotationFont(&font, &parentDimStyle);
        textObject.SetAnnotationBold(bold, &parentDimStyle);
        textObject.SetAnnotationItalic(italic, &parentDimStyle);
        if (!fontName.empty())
            textObject.SetAnnotationFacename(true, Utf8ToWide(fontName), &parentDimStyle);

        auto* textRhinoObject = pDoc->CreateTextObject(textObject, &attrs);
        if (!textRhinoObject)
            throw std::runtime_error("Failed to create text object");

        if (!pDoc->AddObject(textRhinoObject))
        {
            delete textRhinoObject;
            throw std::runtime_error("Failed to add text object to document");
        }

        pDoc->Redraw();

        // --- End factory body ---

        // Read back the effective typography from the persisted annotation
        // so the response reflects what was actually applied (including
        // font-fallback cases), not the request parameters.
        ObjectSnapshot snapshot = CaptureObjectSnapshot(textRhinoObject, pDoc);

        nlohmann::json data = Serializer::SerializeObject(snapshot);

        // Echo effective typography as top-level fields. Sourced from the
        // live annotation's effective dimstyle + annotation object, mirroring
        // what GeometryHandler's AnnotationDetail exposes via /geometry so
        // the two surfaces agree.
        if (const auto* annotation = dynamic_cast<const CRhinoAnnotation*>(textRhinoObject))
        {
            const ON_DimStyle& effStyle = annotation->GetEffectiveDimensionStyle(pDoc);
            const ON_Font& effFont = effStyle.Font();
            data["height"] = effStyle.TextHeight();
            data["font"] = WideToUtf8(effFont.FamilyName());
            data["fontFace"] = WideToUtf8(effFont.FaceName());
            data["bold"] = effFont.IsBold();
            data["italic"] = effFont.IsItalic();
        }

        WriteResult wr;
        wr.success = true;
        wr.data = std::move(data);
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
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
    }
    catch (const std::exception& ex)
    {
        nlohmann::json err = {
            {"errorCode", "operation_failed"},
            {"errorMessage", ex.what()},
        };
        CRookServer::SendErrorData(res, err);
    }
}

// --- POST /annotation/dim-aligned ---------------------------------------

void HandleDimAligned(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto invalidInput = [&](const std::string& message) {
        nlohmann::json err = {
            {"errorCode", "invalid_input"},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // Worker-thread schema validation (Rule 2).

    auto requirePoint = [&](const char* key) -> bool {
        if (!body.contains(key))
        {
            invalidInput(std::string("Missing required field: ") + key);
            return false;
        }
        if (!body[key].is_array() || body[key].size() != 3)
        {
            invalidInput(std::string("'") + key + "' must be an array of exactly 3 numbers");
            return false;
        }
        for (int i = 0; i < 3; ++i)
        {
            if (!body[key][i].is_number())
            {
                invalidInput(std::string("'") + key + "' entries must be numbers");
                return false;
            }
        }
        return true;
    };

    if (!requirePoint("start")) return;
    if (!requirePoint("end")) return;

    if (!body.contains("offset"))
    {
        invalidInput("Missing required field: offset");
        return;
    }
    if (!body["offset"].is_number())
    {
        invalidInput("'offset' must be a number");
        return;
    }

    // `direction` is a LINEAR-specific parameter and has no meaning for
    // ALIGNED (which always measures the direct Euclidean distance with
    // the dim plane tilting to match start→end). Silently accepting it
    // would weaken the explicit LINEAR/ALIGNED route split, so reject
    // with a pointer to the sibling route.
    if (body.contains("direction"))
    {
        invalidInput("'direction' is not accepted by /annotation/dim-aligned — "
                     "ALIGNED measures direct Euclidean distance. Use "
                     "/annotation/dim-linear for projection-direction semantics.");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Create Aligned Dimension");

        ON_3dmObjectAttributes attrs;
        ApplyCommonAttributesStrict(attrs, body, pDoc);

        const ON_3dPoint start = ParsePoint3d(body, "start");
        const ON_3dPoint end = ParsePoint3d(body, "end");
        const double offset = body["offset"].get<double>();

        // Coincident-point rejection via Unitize-fail, reusing the legacy
        // factory posture at CreateHandler.cpp:586-587 — same tolerance
        // policy (none) as PR-2 for consistency across dim variants.
        ON_3dVector startToEnd = end - start;
        if (!startToEnd.Unitize())
            throw std::invalid_argument("'start' and 'end' must be distinct points");

        // ALIGNED measuredValue is the direct Euclidean distance between
        // the extension points. Computed from geometry math here and
        // echoed in the response — never read back from PlainText.
        const double measuredValue = (end - start).Length();

        // Perpendicular-in-plane derived from startToEnd (the ALIGNED
        // dim plane is determined by the extension points, not by a
        // user direction).
        ON_3dVector perpDir = ON_CrossProduct(startToEnd, ON_3dVector::ZAxis);
        if (!perpDir.Unitize())
        {
            perpDir = ON_CrossProduct(startToEnd, ON_3dVector::YAxis);
            if (!perpDir.Unitize())
                throw std::runtime_error("Failed to construct aligned dimension plane");
        }

        const ON_3dPoint mid = start + 0.5 * (end - start);
        const ON_3dPoint offsetPoint = mid + offset * perpDir;
        ON_3dVector planeNormal = ON_CrossProduct(startToEnd, perpDir);
        if (!planeNormal.Unitize())
            planeNormal = ON_3dVector::ZAxis;

        // ALIGNED uses the ON_3dPoint `dim_line_point` overload of
        // AddDimLinearObject (rhinoSdkDoc.h:3410), which PR-2 empirically
        // verified produces AnnotationType::Aligned. This is the same
        // overload the legacy /create?type=DIMENSION_LINEAR factory at
        // CreateHandler.cpp:604 uses — confirming that legacy actually
        // produces ALIGNED despite the "LINEAR" naming. PR-3 ships this
        // path as the correct ALIGNED route; PR-2's ON_Line overload
        // ships as the correct LINEAR route.
        const auto dimContext = pDoc->DimStyleContext();
        auto* obj = pDoc->AddDimLinearObject(
            start,
            end,
            offsetPoint,
            planeNormal,
            &dimContext.CurrentDimStyle(),
            &attrs);
        if (!obj)
            throw std::runtime_error("Failed to create aligned dimension");

        pDoc->Redraw();

        // Read back the effective annotationType from the live object.
        // If this comes back as anything other than "AlignedDimension",
        // the SDK construction path misclassified and the PR-3 contract
        // is broken (test-red, not downgraded contract).
        ObjectSnapshot snapshot = CaptureObjectSnapshot(obj, pDoc);
        nlohmann::json data = Serializer::SerializeObject(snapshot);

        if (const auto* annotation = dynamic_cast<const CRhinoAnnotation*>(obj))
        {
            // Third local copy of the ON::AnnotationType → wire-string
            // mapping (also in GeometryHandler.cpp:19-36 and
            // HandleDimLinear above). Accepted conscious debt per Codex
            // 2026-04-19 review of PR-2: promotion to a shared helper
            // waits for a concrete 4th-caller trigger rather than
            // speculative extraction. The parked work-queue entry tracks
            // the trigger.
            const ON::AnnotationType at = annotation->AnnotationType();
            switch (at)
            {
            case ON::AnnotationType::Aligned:      data["annotationType"] = "AlignedDimension"; break;
            case ON::AnnotationType::Rotated:      data["annotationType"] = "LinearDimension"; break;
            default:                                data["annotationType"] = "Annotation"; break;
            }
        }
        data["measuredValue"] = measuredValue;

        WriteResult wr;
        wr.success = true;
        wr.data = std::move(data);
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
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
    }
    catch (const std::exception& ex)
    {
        nlohmann::json err = {
            {"errorCode", "operation_failed"},
            {"errorMessage", ex.what()},
        };
        CRookServer::SendErrorData(res, err);
    }
}

// --- POST /annotation/dim-linear ----------------------------------------

void HandleDimLinear(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto invalidInput = [&](const std::string& message) {
        nlohmann::json err = {
            {"errorCode", "invalid_input"},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // Worker-thread schema validation (Rule 2).

    auto requirePoint = [&](const char* key) -> bool {
        if (!body.contains(key))
        {
            invalidInput(std::string("Missing required field: ") + key);
            return false;
        }
        if (!body[key].is_array() || body[key].size() != 3)
        {
            invalidInput(std::string("'") + key + "' must be an array of exactly 3 numbers");
            return false;
        }
        for (int i = 0; i < 3; ++i)
        {
            if (!body[key][i].is_number())
            {
                invalidInput(std::string("'") + key + "' entries must be numbers");
                return false;
            }
        }
        return true;
    };

    if (!requirePoint("start")) return;
    if (!requirePoint("end")) return;

    if (!body.contains("offset"))
    {
        invalidInput("Missing required field: offset");
        return;
    }
    if (!body["offset"].is_number())
    {
        invalidInput("'offset' must be a number");
        return;
    }

    if (body.contains("direction"))
    {
        if (!body["direction"].is_array() || body["direction"].size() != 3)
        {
            invalidInput("'direction' must be an array of exactly 3 numbers");
            return;
        }
        for (int i = 0; i < 3; ++i)
        {
            if (!body["direction"][i].is_number())
            {
                invalidInput("'direction' entries must be numbers");
                return;
            }
        }
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Create Linear Dimension");

        ON_3dmObjectAttributes attrs;
        ApplyCommonAttributesStrict(attrs, body, pDoc);

        const ON_3dPoint start = ParsePoint3d(body, "start");
        const ON_3dPoint end = ParsePoint3d(body, "end");
        const double offset = body["offset"].get<double>();

        // Coincident-point rejection via Unitize-fail, reusing the legacy
        // CreateLinearDimension factory posture at CreateHandler.cpp:586-587
        // — no custom tolerance policy.
        ON_3dVector startToEnd = end - start;
        if (!startToEnd.Unitize())
            throw std::invalid_argument("'start' and 'end' must be distinct points");

        // Parse + unitize the user-specified projection direction (default
        // world X). Same Unitize-fail posture gates zero-length inputs.
        ON_3dVector projectionDir;
        if (body.contains("direction"))
        {
            projectionDir = ON_3dVector(
                body["direction"][0].get<double>(),
                body["direction"][1].get<double>(),
                body["direction"][2].get<double>());
        }
        else
        {
            projectionDir = ON_3dVector::XAxis;
        }
        if (!projectionDir.Unitize())
            throw std::invalid_argument("'direction' must be non-zero");

        // LINEAR semantics: measured value is the PROJECTION of (end - start)
        // onto the user direction. Computed from the inputs here and echoed
        // in the response — never read back from the dim's PlainText, which
        // is presentation (dimstyle formatting, rounding, prefixes/suffixes
        // could corrupt numeric parsing).
        const ON_3dVector rawDelta = end - start;
        const double signedProjection = rawDelta * projectionDir;
        const double measuredValue = std::fabs(signedProjection);

        // Construct the dim plane so its X-axis IS the projection direction.
        // This orients the dim geometry to read along the user's direction
        // (LINEAR/Rotated semantics), not along start→end (ALIGNED).
        ON_3dVector perpDir = ON_CrossProduct(projectionDir, ON_3dVector::ZAxis);
        if (!perpDir.Unitize())
        {
            perpDir = ON_CrossProduct(projectionDir, ON_3dVector::YAxis);
            if (!perpDir.Unitize())
                throw std::runtime_error("Failed to construct linear dimension plane");
        }

        const ON_3dPoint mid = start + 0.5 * (end - start);
        const ON_3dPoint offsetPoint = mid + offset * perpDir;
        ON_3dVector planeNormal = ON_CrossProduct(projectionDir, perpDir);
        if (!planeNormal.Unitize())
            planeNormal = ON_3dVector::ZAxis;

        // CRhinoDoc has two AddDimLinearObject overloads (rhinoSdkDoc.h:3410
        // and :3444):
        //   - The `dimension_line_point` (ON_3dPoint) overload produces an
        //     ALIGNED dimension (dim line implicit, parallel to ext0→ext1).
        //   - The `dimension_line` (ON_Line) overload produces a ROTATED /
        //     LINEAR dimension (dim line explicit, can be at any angle).
        // PR-2's contract requires LINEAR semantics, so we construct an
        // explicit dim line parallel to projectionDir and use the second
        // overload. Empirical verification 2026-04-19: the ON_3dPoint
        // overload returned AnnotationType::Aligned; the ON_Line overload
        // returns AnnotationType::Rotated.
        const ON_Line dimLine(offsetPoint, offsetPoint + projectionDir);
        const auto dimContext = pDoc->DimStyleContext();
        auto* obj = pDoc->AddDimLinearObject(
            start,
            end,
            dimLine,
            planeNormal,
            &dimContext.CurrentDimStyle(),
            &attrs);
        if (!obj)
            throw std::runtime_error("Failed to create linear dimension");

        pDoc->Redraw();

        // Read back the effective annotationType from the live object. The
        // AddDimLinearObject API internally chooses LINEAR vs ALIGNED based
        // on the plane/direction geometry; this echo pins the observed
        // classification so the PR-2 contract is enforced by the test
        // suite. If it comes back as "AlignedDimension" for inputs that
        // LINEAR should handle (direction not parallel to start→end), the
        // factory needs a different SDK construction — that is a test-red
        // failure, not a downgraded contract.
        ObjectSnapshot snapshot = CaptureObjectSnapshot(obj, pDoc);
        nlohmann::json data = Serializer::SerializeObject(snapshot);

        if (const auto* annotation = dynamic_cast<const CRhinoAnnotation*>(obj))
        {
            const ON::AnnotationType at = annotation->AnnotationType();
            // Mirror the exact string used by GeometryHandler.cpp's
            // AnnotationTypeToString (line 19-36) so /annotation/dim-linear
            // and GET /geometry agree on the wire format.
            switch (at)
            {
            case ON::AnnotationType::Aligned:      data["annotationType"] = "AlignedDimension"; break;
            case ON::AnnotationType::Rotated:      data["annotationType"] = "LinearDimension"; break;
            default:                                data["annotationType"] = "Annotation"; break;
            }
        }
        data["measuredValue"] = measuredValue;

        WriteResult wr;
        wr.success = true;
        wr.data = std::move(data);
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
    catch (const std::invalid_argument& ex)
    {
        invalidInput(ex.what());
    }
    catch (const std::exception& ex)
    {
        nlohmann::json err = {
            {"errorCode", "operation_failed"},
            {"errorMessage", ex.what()},
        };
        CRookServer::SendErrorData(res, err);
    }
}

} // namespace Handlers
} // namespace Rook
