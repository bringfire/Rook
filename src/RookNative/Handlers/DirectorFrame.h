// DirectorFrame.h
//
// Shared per-frame primitives for RookVisionDirector.
// Used by both DirectorHandler (frame-capture) and DirectorReplayHandler (live replay).
//
// NOTE: This header is designed to be included AFTER "stdafx.h" which pulls in the
// Rhino SDK (RhinoCommon types) and the nlohmann/json PCH. Do not include standalone.

#pragma once

#include <stdexcept>
#include <string>
#include <vector>

namespace Rook {
namespace Handlers {

// ---------------------------------------------------------------------------
// Error type thrown by frame-validation and pose operations.
// ---------------------------------------------------------------------------
class DirectorFrameValidationError : public std::runtime_error
{
public:
    DirectorFrameValidationError(std::string errorCode, const std::string& message)
        : std::runtime_error(message), code(std::move(errorCode))
    {
    }

    DirectorFrameValidationError(std::string errorCode, const std::string& message,
                                  std::vector<std::string> affectedIds)
        : std::runtime_error(message), code(std::move(errorCode)),
          affectedObjectIds(std::move(affectedIds))
    {
    }

    std::string code;
    std::vector<std::string> affectedObjectIds;
};

// ---------------------------------------------------------------------------
// Shared data structs
// ---------------------------------------------------------------------------
struct FrameObjectTransform
{
    std::string objectId;
    ON_UUID uuid = ON_nil_uuid;
    ON_Xform delta = ON_Xform::IdentityTransformation;
    ON_Xform inverseDelta = ON_Xform::IdentityTransformation;
    ON_BoundingBox sourceBbox;
    std::string sourceObjectType;
    std::string validationStrength;
};

struct FrameCamera
{
    ON_3dPoint location = ON_3dPoint::Origin;
    ON_3dPoint target = ON_3dPoint::Origin;
    ON_3dVector up = ON_3dVector::ZAxis;
    bool hasLensLength = false;
    double lensLength = 0.0;
    bool hasFovDegrees = false;
    double fovDegrees = 0.0;
    bool hasAspect = false;
    double aspect = 0.0;
    bool hasNearFar = false;
    double nearClip = 0.0;
    double farClip = 0.0;
};

// ---------------------------------------------------------------------------
// Parse helpers (pure — no capture-only fields)
// ---------------------------------------------------------------------------
ON_Xform ParseTransformMatrix(const nlohmann::json& transform, const std::string& objectId);
ON_3dPoint ParsePointArray3(const nlohmann::json& value, const std::string& key);
FrameCamera ParseCamera(const nlohmann::json& body);
std::vector<FrameObjectTransform> ParseFrameObjectTransforms(const nlohmann::json& body);

// ---------------------------------------------------------------------------
// Validation helpers
// ---------------------------------------------------------------------------
void ValidateFrameObjects(CRhinoDoc* pDoc, const std::vector<FrameObjectTransform>& objects);
bool BboxAlmostEqual(const ON_BoundingBox& a, const ON_BoundingBox& b, double tolerance);

// ---------------------------------------------------------------------------
// Transform helpers
// ---------------------------------------------------------------------------
bool TransformObjectInPlace(CRhinoDoc* pDoc, const FrameObjectTransform& frameObject,
                            const ON_Xform& xform);

// ---------------------------------------------------------------------------
// Camera application (pure camera-set — no display mode, no capture evidence)
// ---------------------------------------------------------------------------
void SetCameraFromFrame(CRhinoView* pView, const FrameCamera& camera);

// ---------------------------------------------------------------------------
// Viewport comparison and display-mode helpers (dependency closure for guards)
// ---------------------------------------------------------------------------
bool NearlyEqual(double a, double b, double tolerance);
bool PointAlmostEqual(const ON_3dPoint& a, const ON_3dPoint& b, double tolerance);
bool VectorAlmostEqual(const ON_3dVector& a, const ON_3dVector& b, double tolerance);
bool ViewportAlmostEqual(const ON_Viewport& a, const ON_Viewport& b, double tolerance);
ON_UUID CurrentDisplayModeId(CRhinoView* pView);
nlohmann::json DisplayModeToJson(const ON_UUID& modeId);

// ---------------------------------------------------------------------------
// View validation helpers
// ---------------------------------------------------------------------------
std::string Slice1UnsupportedViewMessage(const std::string& source);
void ValidateSlice1ModelRhinoView(const CRhinoView* pView);
void ValidateSlice1NamedView(const ON_3dmView& view, const std::string& name);

// ---------------------------------------------------------------------------
// RAII guard: applies and restores per-object pose transforms.
// Non-copyable and non-movable (double-restore hazard).
// ---------------------------------------------------------------------------
class DirectorObjectPoseGuard
{
public:
    DirectorObjectPoseGuard(CRhinoDoc* pDoc, std::vector<FrameObjectTransform> objects);
    ~DirectorObjectPoseGuard();

    DirectorObjectPoseGuard(const DirectorObjectPoseGuard&) = delete;
    DirectorObjectPoseGuard& operator=(const DirectorObjectPoseGuard&) = delete;
    DirectorObjectPoseGuard(DirectorObjectPoseGuard&&) = delete;
    DirectorObjectPoseGuard& operator=(DirectorObjectPoseGuard&&) = delete;

    void Apply();
    bool Restore(nlohmann::json& evidence);
    bool HasDirtyPartialState() const;
    int AppliedCount() const;

    /// Suppress the destructor's BestEffortRestore — call when leaving the pose applied
    /// intentionally (e.g. replay holds it for the next tick).
    void Disarm() { m_restoreAttempted = true; }

private:
    void BestEffortRestore();

    CRhinoDoc* m_doc = nullptr;
    std::vector<FrameObjectTransform> m_objects;
    std::vector<bool> m_applied;
    std::vector<bool> m_restored;
    bool m_restoreAttempted = false;
};

// ---------------------------------------------------------------------------
// RAII guard: snapshots and restores the active viewport (camera + display mode).
// Non-copyable and non-movable (double-restore hazard).
// ---------------------------------------------------------------------------
class DirectorViewportGuard
{
public:
    explicit DirectorViewportGuard(CRhinoDoc* pDoc);
    ~DirectorViewportGuard();

    DirectorViewportGuard(const DirectorViewportGuard&) = delete;
    DirectorViewportGuard& operator=(const DirectorViewportGuard&) = delete;
    DirectorViewportGuard(DirectorViewportGuard&&) = delete;
    DirectorViewportGuard& operator=(DirectorViewportGuard&&) = delete;

    CRhinoView* View() const;
    bool Restore(nlohmann::json& evidence);
    bool IsRestored() const;

    /// Suppress the destructor's BestEffortRestore — call when replay intentionally holds
    /// the modified viewport state for the next tick.
    void Disarm() { m_restoreAttempted = true; }

private:
    bool RestoreNow();
    void BestEffortRestore();

    static constexpr double kViewportTolerance = 1.0e-4;

    CRhinoView* m_view = nullptr;
    ON_Viewport m_savedViewport;
    ON_UUID m_savedDisplayModeId = ON_nil_uuid;
    bool m_restoreAttempted = false;
    bool m_restored = false;
    bool m_displayRestored = false;
    bool m_displayRestoreSetAccepted = true;
    bool m_displayRestoreReadbackMatches = false;
    ON_UUID m_displayRestoreReadbackModeId = ON_nil_uuid;
};

} // namespace Handlers
} // namespace Rook
