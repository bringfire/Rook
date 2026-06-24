// DirectorFrame.cpp
//
// Shared per-frame primitives for RookVisionDirector.
// Used by both DirectorHandler (frame-capture) and DirectorReplayHandler (live replay).

#include "stdafx.h"
#include "Handlers/DirectorFrame.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace Rook {
namespace Handlers {

// ---------------------------------------------------------------------------
// Scalar / point / vector comparison helpers
// ---------------------------------------------------------------------------

bool NearlyEqual(double a, double b, double tolerance)
{
    return std::fabs(a - b) <= tolerance;
}

bool PointAlmostEqual(const ON_3dPoint& a, const ON_3dPoint& b, double tolerance)
{
    return NearlyEqual(a.x, b.x, tolerance) &&
        NearlyEqual(a.y, b.y, tolerance) &&
        NearlyEqual(a.z, b.z, tolerance);
}

bool VectorAlmostEqual(const ON_3dVector& a, const ON_3dVector& b, double tolerance)
{
    return NearlyEqual(a.x, b.x, tolerance) &&
        NearlyEqual(a.y, b.y, tolerance) &&
        NearlyEqual(a.z, b.z, tolerance);
}

bool ViewportAlmostEqual(const ON_Viewport& a, const ON_Viewport& b, double tolerance)
{
    if (a.IsPerspectiveProjection() != b.IsPerspectiveProjection())
        return false;
    if (a.IsParallelProjection() != b.IsParallelProjection())
        return false;
    if (!PointAlmostEqual(a.CameraLocation(), b.CameraLocation(), tolerance))
        return false;
    if (!PointAlmostEqual(a.TargetPoint(), b.TargetPoint(), tolerance))
        return false;
    if (!VectorAlmostEqual(a.CameraUp(), b.CameraUp(), tolerance))
        return false;

    double aAspect = 0.0;
    double bAspect = 0.0;
    if (a.GetFrustumAspect(aAspect) && b.GetFrustumAspect(bAspect) && !NearlyEqual(aAspect, bAspect, tolerance))
        return false;

    return NearlyEqual(a.FrustumLeft(), b.FrustumLeft(), tolerance) &&
        NearlyEqual(a.FrustumRight(), b.FrustumRight(), tolerance) &&
        NearlyEqual(a.FrustumBottom(), b.FrustumBottom(), tolerance) &&
        NearlyEqual(a.FrustumTop(), b.FrustumTop(), tolerance) &&
        NearlyEqual(a.FrustumNear(), b.FrustumNear(), tolerance) &&
        NearlyEqual(a.FrustumFar(), b.FrustumFar(), tolerance);
}

// ---------------------------------------------------------------------------
// Display-mode helpers
// ---------------------------------------------------------------------------

ON_UUID CurrentDisplayModeId(CRhinoView* pView)
{
    if (!pView)
        return ON_nil_uuid;
    return pView->ActiveViewport().m_v.m_display_mode_id;
}

nlohmann::json DisplayModeToJson(const ON_UUID& modeId)
{
    nlohmann::json data;
    data["id"] = ON_UuidIsNil(modeId) ? nlohmann::json(nullptr) : nlohmann::json(UuidToString(modeId));

    const CDisplayPipelineAttributes* pAttrs = ON_UuidIsNil(modeId)
        ? nullptr
        : CRhinoDisplayAttrsMgr::FindDisplayAttrs(modeId);
    data["name"] = pAttrs ? nlohmann::json(WideToUtf8(pAttrs->EnglishName())) : nlohmann::json(nullptr);
    return data;
}

// ---------------------------------------------------------------------------
// View validation helpers
// ---------------------------------------------------------------------------

std::string Slice1UnsupportedViewMessage(const std::string& source)
{
    return "RookVisionDirector slice1 only supports model views; " + source +
        " resolved to a page, layout, detail, UV, block editor, or otherwise unsupported view";
}

void ValidateSlice1ModelRhinoView(const CRhinoView* pView)
{
    if (!pView)
        throw std::runtime_error("No active view");
    if (pView->IsPageView() || pView->RhinoViewType() != CRhinoView::rhino_view_type)
        throw DirectorFrameValidationError("unsupported_view", Slice1UnsupportedViewMessage("active_view"));
}

void ValidateSlice1NamedView(const ON_3dmView& view, const std::string& name)
{
    if (view.m_view_type != ON::model_view_type)
        throw DirectorFrameValidationError(
            "unsupported_view",
            Slice1UnsupportedViewMessage("named_view '" + name + "'"));
}

// ---------------------------------------------------------------------------
// Parse helpers
// ---------------------------------------------------------------------------

ON_3dPoint ParsePointArray3(const nlohmann::json& value, const std::string& key)
{
    if (!value.is_array() || value.size() != 3)
        throw DirectorFrameValidationError("invalid_input", key + " must be a 3-number array");

    for (size_t i = 0; i < 3; ++i)
    {
        if (!value[i].is_number())
            throw DirectorFrameValidationError("invalid_input", key + " must be a 3-number array");
    }

    return ON_3dPoint(value[0].get<double>(), value[1].get<double>(), value[2].get<double>());
}

ON_Xform ParseTransformMatrix(const nlohmann::json& transform, const std::string& objectId)
{
    if (!transform.is_array() || transform.size() != 4)
        throw DirectorFrameValidationError("invalid_input", "transform must be a 4x4 numeric matrix", { objectId });

    ON_Xform xform = ON_Xform::IdentityTransformation;
    for (size_t rowIndex = 0; rowIndex < 4; ++rowIndex)
    {
        const auto& row = transform[rowIndex];
        if (!row.is_array() || row.size() != 4)
            throw DirectorFrameValidationError("invalid_input", "transform must be a 4x4 numeric matrix", { objectId });
        for (size_t colIndex = 0; colIndex < 4; ++colIndex)
        {
            const auto& value = row[colIndex];
            if (!value.is_number())
                throw DirectorFrameValidationError("invalid_input", "transform must be a 4x4 numeric matrix", { objectId });
            double numeric = value.get<double>();
            if (!std::isfinite(numeric))
                throw DirectorFrameValidationError("invalid_input", "transform matrix values must be finite", { objectId });
            xform.m_xform[rowIndex][colIndex] = numeric;
        }
    }

    return xform;
}

namespace {

bool IsFinitePoint(const ON_3dPoint& point)
{
    return std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z);
}

bool IsFiniteVector(const ON_3dVector& vector)
{
    return std::isfinite(vector.x) && std::isfinite(vector.y) && std::isfinite(vector.z);
}

bool HasPositiveOptionalNumber(const nlohmann::json& object, const std::string& key)
{
    if (!object.contains(key) || object[key].is_null())
        return false;

    if (!object[key].is_number())
        throw DirectorFrameValidationError("invalid_input", key + " must be a positive number when provided");

    double value = object[key].get<double>();
    if (!std::isfinite(value) || value <= 0.0)
        throw DirectorFrameValidationError("invalid_input", key + " must be a positive finite number");

    return true;
}

double GetPositiveOptionalNumber(const nlohmann::json& object, const std::string& key)
{
    return object[key].get<double>();
}

bool HasValidFovDegrees(const nlohmann::json& object)
{
    if (!object.contains("fov_degrees") || object["fov_degrees"].is_null())
        return false;

    if (!object["fov_degrees"].is_number())
        throw DirectorFrameValidationError("invalid_input", "fov_degrees must be a positive number when provided");

    double value = object["fov_degrees"].get<double>();
    if (!std::isfinite(value) || value <= 0.0 || value >= 180.0)
        throw DirectorFrameValidationError("invalid_input", "fov_degrees must be finite and between 0 and 180");

    return true;
}

double GetFovDegrees(const nlohmann::json& object)
{
    return object["fov_degrees"].get<double>();
}

bool HasPositiveOptionalFiniteNumber(const nlohmann::json& object, const std::string& key)
{
    if (!object.contains(key) || object[key].is_null())
        return false;

    if (!object[key].is_number())
        throw DirectorFrameValidationError("invalid_input", key + " must be a positive number when provided");

    double value = object[key].get<double>();
    if (!std::isfinite(value) || value <= 0.0)
        throw DirectorFrameValidationError("invalid_input", key + " must be a positive finite number");

    return true;
}

} // anonymous namespace

FrameCamera ParseCamera(const nlohmann::json& body)
{
    if (!body.contains("camera") || !body["camera"].is_object())
        throw DirectorFrameValidationError("invalid_input", "camera must be an object");

    const auto& camera = body["camera"];
    if (!camera.contains("projection") || !camera["projection"].is_string())
        throw DirectorFrameValidationError("invalid_input", "camera.projection is required");

    std::string projection = camera["projection"].get<std::string>();
    if (projection != "perspective")
        throw DirectorFrameValidationError("unsupported_projection", "Slice 1 frame-capture supports perspective cameras only");

    ON_3dPoint location = ParsePointArray3(camera.value("location", nlohmann::json()), "camera.location");
    ON_3dPoint target = ParsePointArray3(camera.value("target", nlohmann::json()), "camera.target");
    ON_3dPoint upPoint = ParsePointArray3(camera.value("up", nlohmann::json()), "camera.up");
    ON_3dVector up(upPoint.x, upPoint.y, upPoint.z);
    ON_3dVector direction = target - location;

    if (!IsFinitePoint(location) || !IsFinitePoint(target) || !IsFiniteVector(up))
        throw DirectorFrameValidationError("invalid_input", "camera vectors must be finite");
    if (!direction.Unitize())
        throw DirectorFrameValidationError("invalid_input", "camera location and target must differ");
    if (!up.Unitize())
        throw DirectorFrameValidationError("invalid_input", "camera.up must be nonzero");

    const bool hasLensLength = HasPositiveOptionalNumber(camera, "lens_length");
    const bool hasFovDegrees = HasValidFovDegrees(camera);
    if (!hasLensLength && !hasFovDegrees)
        throw DirectorFrameValidationError("invalid_input", "perspective camera requires positive lens_length or fov_degrees");

    const bool hasAspect = HasPositiveOptionalFiniteNumber(camera, "aspect");
    const bool hasNearClip = HasPositiveOptionalFiniteNumber(camera, "near_clip");
    const bool hasFarClip = HasPositiveOptionalFiniteNumber(camera, "far_clip");
    if (hasNearClip != hasFarClip)
        throw DirectorFrameValidationError("invalid_input", "near_clip and far_clip must be provided together");
    if (hasNearClip && camera["near_clip"].get<double>() >= camera["far_clip"].get<double>())
        throw DirectorFrameValidationError("invalid_input", "near_clip must be less than far_clip");

    FrameCamera parsed;
    parsed.location = location;
    parsed.target = target;
    parsed.up = up;
    parsed.hasLensLength = hasLensLength;
    parsed.lensLength = hasLensLength ? GetPositiveOptionalNumber(camera, "lens_length") : 0.0;
    parsed.hasFovDegrees = hasFovDegrees;
    parsed.fovDegrees = hasFovDegrees ? GetFovDegrees(camera) : 0.0;
    parsed.hasAspect = hasAspect;
    parsed.aspect = hasAspect ? camera["aspect"].get<double>() : 0.0;
    parsed.hasNearFar = hasNearClip && hasFarClip;
    parsed.nearClip = parsed.hasNearFar ? camera["near_clip"].get<double>() : 0.0;
    parsed.farClip = parsed.hasNearFar ? camera["far_clip"].get<double>() : 0.0;
    return parsed;
}

std::vector<FrameObjectTransform> ParseFrameObjectTransforms(const nlohmann::json& body)
{
    if (!body.contains("object_transforms") || !body["object_transforms"].is_array())
        throw DirectorFrameValidationError("invalid_input", "object_transforms must be a non-empty array");

    const auto& transforms = body["object_transforms"];
    if (transforms.empty())
        throw DirectorFrameValidationError("invalid_input", "object_transforms must be a non-empty array");

    std::vector<FrameObjectTransform> parsed;
    parsed.reserve(transforms.size());

    for (const auto& item : transforms)
    {
        if (!item.is_object())
            throw DirectorFrameValidationError("invalid_input", "object_transforms entries must be objects");
        if (!item.contains("object_id") || !item["object_id"].is_string())
            throw DirectorFrameValidationError("invalid_input", "object_transforms[].object_id is required");

        FrameObjectTransform frameObject;
        frameObject.objectId = item["object_id"].get<std::string>();
        frameObject.uuid = ON_UuidFromString(frameObject.objectId.c_str());
        if (ON_UuidIsNil(frameObject.uuid))
            throw DirectorFrameValidationError("invalid_input", "Invalid object id: " + frameObject.objectId, { frameObject.objectId });

        if (!item.contains("transform"))
            throw DirectorFrameValidationError("invalid_input", "object_transforms[].transform is required", { frameObject.objectId });
        frameObject.delta = ParseTransformMatrix(item["transform"], frameObject.objectId);
        frameObject.inverseDelta = frameObject.delta;
        if (!frameObject.inverseDelta.Invert())
            throw DirectorFrameValidationError("invalid_input", "object transform must be invertible", { frameObject.objectId });

        if (!item.contains("source_state") || !item["source_state"].is_object())
            throw DirectorFrameValidationError("invalid_input", "object_transforms[].source_state is required", { frameObject.objectId });

        const auto& sourceState = item["source_state"];
        if (!sourceState.contains("validation_strength") || !sourceState["validation_strength"].is_string())
            throw DirectorFrameValidationError("invalid_input", "source_state.validation_strength is required", { frameObject.objectId });
        frameObject.validationStrength = sourceState["validation_strength"].get<std::string>();
        if (frameObject.validationStrength != "bbox_only")
            throw DirectorFrameValidationError("invalid_input", "source_state.validation_strength must be bbox_only for slice1", { frameObject.objectId });

        ON_3dPoint bboxMin = ParsePointArray3(sourceState.value("bbox_min", nlohmann::json()), "source_state.bbox_min");
        ON_3dPoint bboxMax = ParsePointArray3(sourceState.value("bbox_max", nlohmann::json()), "source_state.bbox_max");
        frameObject.sourceBbox = ON_BoundingBox(bboxMin, bboxMax);
        if (!frameObject.sourceBbox.IsValid())
            throw DirectorFrameValidationError("invalid_input", "source_state bbox is invalid", { frameObject.objectId });

        parsed.push_back(frameObject);
    }

    return parsed;
}

// ---------------------------------------------------------------------------
// Validation helpers
// ---------------------------------------------------------------------------

bool BboxAlmostEqual(const ON_BoundingBox& a, const ON_BoundingBox& b, double tolerance)
{
    return std::fabs(a.m_min.x - b.m_min.x) <= tolerance &&
        std::fabs(a.m_min.y - b.m_min.y) <= tolerance &&
        std::fabs(a.m_min.z - b.m_min.z) <= tolerance &&
        std::fabs(a.m_max.x - b.m_max.x) <= tolerance &&
        std::fabs(a.m_max.y - b.m_max.y) <= tolerance &&
        std::fabs(a.m_max.z - b.m_max.z) <= tolerance;
}

void ValidateFrameObjects(CRhinoDoc* pDoc, const std::vector<FrameObjectTransform>& objects)
{
    constexpr double kBboxTolerance = 1.0e-4;
    for (const FrameObjectTransform& frameObject : objects)
    {
        const CRhinoObject* obj = pDoc->LookupObject(frameObject.uuid);
        if (!obj || obj->IsDeleted())
            throw DirectorFrameValidationError("invalid_input", "Object not found: " + frameObject.objectId, { frameObject.objectId });

        ON_BoundingBox currentBbox = obj->BoundingBox();
        if (!currentBbox.IsValid())
            throw DirectorFrameValidationError("invalid_input", "Object has invalid bounding box: " + frameObject.objectId, { frameObject.objectId });

        if (!BboxAlmostEqual(currentBbox, frameObject.sourceBbox, kBboxTolerance))
            throw DirectorFrameValidationError("invalid_input", "Object source_state bbox does not match current document state", { frameObject.objectId });
    }
}

// ---------------------------------------------------------------------------
// Transform helpers
// ---------------------------------------------------------------------------

bool TransformObjectInPlace(CRhinoDoc* pDoc, const FrameObjectTransform& frameObject, const ON_Xform& xform)
{
    const CRhinoObject* obj = pDoc->LookupObject(frameObject.uuid);
    if (!obj || obj->IsDeleted())
        return false;

    CRhinoObjRef objRef(obj);
    return pDoc->TransformObject(objRef, xform, true, false, true);
}

// ---------------------------------------------------------------------------
// Pure camera-set (no display mode, no evidence JSON — shared with replay)
// ---------------------------------------------------------------------------

void SetCameraFromFrame(CRhinoView* pView, const FrameCamera& camera)
{
    if (!pView)
        throw std::runtime_error("No active view");

    CRhinoViewport& rhinoViewport = pView->ActiveViewport();
    ON_Viewport targetViewport = rhinoViewport.VP();

    ON_3dVector direction = camera.target - camera.location;
    if (!direction.Unitize())
        throw DirectorFrameValidationError("invalid_input", "camera location and target must differ");

    targetViewport.SetProjection(ON::perspective_view);
    if (!targetViewport.SetCameraLocation(camera.location))
        throw DirectorFrameValidationError("invalid_input", "Failed to set camera location");
    if (!targetViewport.SetCameraDirection(direction))
        throw DirectorFrameValidationError("invalid_input", "Failed to set camera direction");
    if (!targetViewport.SetCameraUp(camera.up))
        throw DirectorFrameValidationError("invalid_input", "Failed to set camera up vector");
    targetViewport.SetTargetPoint(camera.target);

    bool cameraOpticsApplied = false;
    if (camera.hasLensLength)
        cameraOpticsApplied = targetViewport.SetCamera35mmLensLength(camera.lensLength);
    if (!cameraOpticsApplied && camera.hasFovDegrees)
    {
        const double halfAngleRadians = (camera.fovDegrees * ON_PI / 180.0) / 2.0;
        cameraOpticsApplied = targetViewport.SetCameraAngle(halfAngleRadians);
    }
    if (!cameraOpticsApplied)
        throw DirectorFrameValidationError("invalid_input", "Failed to apply perspective camera optics");
    if (camera.hasAspect && !targetViewport.SetFrustumAspect(camera.aspect))
        throw DirectorFrameValidationError("invalid_input", "Failed to apply camera aspect");
    if (camera.hasNearFar && !targetViewport.SetFrustumNearFar(camera.nearClip, camera.farClip))
        throw DirectorFrameValidationError("invalid_input", "Failed to apply camera near/far clipping");

    rhinoViewport.SetVP(targetViewport, true, false);
    pView->Redraw();
}

// ---------------------------------------------------------------------------
// DirectorObjectPoseGuard implementation
// ---------------------------------------------------------------------------

DirectorObjectPoseGuard::DirectorObjectPoseGuard(CRhinoDoc* pDoc, std::vector<FrameObjectTransform> objects)
    : m_doc(pDoc), m_objects(std::move(objects))
{
    m_applied.resize(m_objects.size(), false);
    m_restored.resize(m_objects.size(), false);
}

DirectorObjectPoseGuard::~DirectorObjectPoseGuard()
{
    if (!m_restoreAttempted)
        BestEffortRestore();
}

void DirectorObjectPoseGuard::Apply()
{
    for (size_t i = 0; i < m_objects.size(); ++i)
    {
        if (!TransformObjectInPlace(m_doc, m_objects[i], m_objects[i].delta))
            throw DirectorFrameValidationError(
                "native_frame_failed",
                "Failed to apply transform for object: " + m_objects[i].objectId,
                { m_objects[i].objectId });
        m_applied[i] = true;
    }
    if (m_doc)
        m_doc->Redraw();
}

bool DirectorObjectPoseGuard::Restore(nlohmann::json& evidence)
{
    m_restoreAttempted = true;
    int restoredCount = 0;
    nlohmann::json details = nlohmann::json::array();

    for (int i = static_cast<int>(m_objects.size()) - 1; i >= 0; --i)
    {
        const FrameObjectTransform& object = m_objects[static_cast<size_t>(i)];
        nlohmann::json detail;
        detail["object_id"] = object.objectId;
        detail["applied"] = m_applied[static_cast<size_t>(i)];
        detail["restored"] = false;
        detail["validation_strength"] = object.validationStrength;

        if (!m_applied[static_cast<size_t>(i)])
        {
            detail["restored"] = true;
            m_restored[static_cast<size_t>(i)] = true;
            details.push_back(std::move(detail));
            ++restoredCount;
            continue;
        }

        bool transformedBack = false;
        try
        {
            transformedBack = TransformObjectInPlace(m_doc, object, object.inverseDelta);
        }
        catch (const std::exception& ex)
        {
            detail["restore_error"] = ex.what();
        }

        if (!transformedBack)
        {
            detail["restore_error"] = detail.value("restore_error", "restore transform failed");
            details.push_back(std::move(detail));
            continue;
        }

        const CRhinoObject* restoredObj = m_doc ? m_doc->LookupObject(object.uuid) : nullptr;
        if (!restoredObj || restoredObj->IsDeleted())
        {
            detail["restore_error"] = "object not found after restore";
            details.push_back(std::move(detail));
            continue;
        }

        ON_BoundingBox restoredBbox = restoredObj->BoundingBox();
        if (!restoredBbox.IsValid() || !BboxAlmostEqual(restoredBbox, object.sourceBbox, kBboxTolerance))
        {
            detail["restore_error"] = "restored bbox did not match source bbox";
            details.push_back(std::move(detail));
            continue;
        }

        detail["restored"] = true;
        m_restored[static_cast<size_t>(i)] = true;
        ++restoredCount;
        details.push_back(std::move(detail));
    }

    if (m_doc)
        m_doc->Redraw();

    evidence["objects"]["requested"] = static_cast<int>(m_objects.size());
    evidence["objects"]["applied"] = AppliedCount();
    evidence["objects"]["restored"] = restoredCount;
    evidence["objects"]["validation_strength"] = "bbox_only";
    evidence["objects"]["details"] = std::move(details);
    return restoredCount == static_cast<int>(m_objects.size());
}

bool DirectorObjectPoseGuard::HasDirtyPartialState() const
{
    for (size_t i = 0; i < m_objects.size(); ++i)
    {
        if (m_applied[i] && !m_restored[i])
            return true;
    }
    return false;
}

int DirectorObjectPoseGuard::AppliedCount() const
{
    return static_cast<int>(std::count(m_applied.begin(), m_applied.end(), true));
}

void DirectorObjectPoseGuard::BestEffortRestore()
{
    m_restoreAttempted = true;
    for (int i = static_cast<int>(m_objects.size()) - 1; i >= 0; --i)
    {
        if (!m_applied[static_cast<size_t>(i)] || m_restored[static_cast<size_t>(i)])
            continue;
        try
        {
            if (TransformObjectInPlace(m_doc, m_objects[static_cast<size_t>(i)], m_objects[static_cast<size_t>(i)].inverseDelta))
                m_restored[static_cast<size_t>(i)] = true;
        }
        catch (...)
        {
        }
    }
    if (m_doc)
        m_doc->Redraw();
}

// ---------------------------------------------------------------------------
// DirectorViewportGuard implementation
// ---------------------------------------------------------------------------

DirectorViewportGuard::DirectorViewportGuard(CRhinoDoc* pDoc)
{
    if (!pDoc)
        throw std::runtime_error("No active document");

    m_view = pDoc->ActiveView();
    if (!m_view)
        throw std::runtime_error("No active view");
    ValidateSlice1ModelRhinoView(m_view);

    m_savedViewport = m_view->ActiveViewport().VP();
    m_savedDisplayModeId = CurrentDisplayModeId(m_view);
}

DirectorViewportGuard::~DirectorViewportGuard()
{
    if (!m_restoreAttempted)
        BestEffortRestore();
}

CRhinoView* DirectorViewportGuard::View() const
{
    return m_view;
}

bool DirectorViewportGuard::Restore(nlohmann::json& evidence)
{
    m_restoreAttempted = true;
    bool restored = false;
    std::string restoreError;
    try
    {
        restored = RestoreNow();
    }
    catch (const std::exception& ex)
    {
        restoreError = ex.what();
    }

    evidence["viewport"]["restored"] = restored;
    evidence["viewport"]["restore_verified"] = restored;
    evidence["display"]["restored"] = m_displayRestored;
    evidence["display"]["restore_set_accepted"] = m_displayRestoreSetAccepted;
    evidence["display"]["restore_readback_mode"] = DisplayModeToJson(m_displayRestoreReadbackModeId);
    evidence["display"]["restore_readback_matches"] = m_displayRestoreReadbackMatches;
    if (!restoreError.empty())
        evidence["viewport"]["restore_error"] = restoreError;
    m_restored = restored;
    return restored;
}

bool DirectorViewportGuard::IsRestored() const
{
    return m_restored;
}

bool DirectorViewportGuard::RestoreNow()
{
    if (!m_view)
        return false;

    CRhinoViewport& vp = m_view->ActiveViewport();
    vp.SetVP(m_savedViewport, true, false);
    bool displaySetAccepted = true;
    if (!ON_UuidIsNil(m_savedDisplayModeId))
        displaySetAccepted = vp.SetDisplayMode(m_savedDisplayModeId);
    m_view->Redraw();

    const bool viewportRestored = ViewportAlmostEqual(vp.VP(), m_savedViewport, kViewportTolerance);
    const ON_UUID currentDisplayModeId = CurrentDisplayModeId(m_view);
    m_displayRestoreSetAccepted = displaySetAccepted;
    m_displayRestoreReadbackModeId = currentDisplayModeId;
    m_displayRestoreReadbackMatches = ON_UuidIsNil(m_savedDisplayModeId) ||
        ON_UuidCompare(currentDisplayModeId, m_savedDisplayModeId) == 0;
    m_displayRestored = ON_UuidIsNil(m_savedDisplayModeId) ||
        m_displayRestoreReadbackMatches;
    return viewportRestored && m_displayRestored;
}

void DirectorViewportGuard::BestEffortRestore()
{
    m_restoreAttempted = true;
    try
    {
        m_restored = RestoreNow();
    }
    catch (...)
    {
    }
}

} // namespace Handlers
} // namespace Rook
