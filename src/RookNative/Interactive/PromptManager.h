// PromptManager.h
//
// User interaction prompts: point picking, object selection, distance.
// Each prompt runs a modal CRhinoGetPoint/CRhinoGetObject on the main thread
// via fire-and-forget Dispatch + condition_variable waiting on the HTTP thread.
//
// The WndProc subclass (Phase 5A) ensures Dispatch queue drains even during
// the modal message loops that GetPoint/GetObject create.
//
// Key pattern:
//   Shared state is heap-allocated via shared_ptr — both threads hold a copy,
//   so the state survives even if the HTTP thread times out and returns.
//
//   HTTP thread → Dispatch(lambda capturing shared_ptr) → wait on cv (timeout)
//   Main thread → GetPoint() blocks in modal loop
//   Main thread → user picks → lambda sets result + notifies cv (inside lock)
//   HTTP thread → cv wakes → return result
//   On timeout  → post VK_ESCAPE (no captures) → lambda finishes safely
//                  against heap state (shared_ptr prevents dangling)

#pragma once

#include <string>
#include <vector>
#include <array>

namespace Rook {

// ─── Result Types ───────────────────────────────────────────────────

struct PointResult
{
    bool success = false;
    bool cancelled = false;
    std::string error;
    std::array<double, 3> point{};
};

struct ObjectResult
{
    bool success = false;
    bool cancelled = false;
    std::string error;
    std::string id;
    std::string type;
    std::string name;
    std::string layer;
    std::array<double, 3> pickPoint{};
    bool hasPickPoint = false;
};

struct MultiObjectResult
{
    bool success = false;
    bool cancelled = false;
    std::string error;
    std::vector<ObjectResult> objects;
};

struct SubObjectResult
{
    bool success = false;
    bool cancelled = false;
    std::string error;
    std::string parentId;
    std::string parentType;
    std::string componentType;  // "brep_face", "brep_edge", "brep_vertex"
    int componentIndex = -1;
    // Geometry info (populated based on component type)
    double area = 0.0;
    std::array<double, 3> centroid{};
    std::array<double, 3> normal{};
    double length = 0.0;
    std::array<double, 3> startPoint{};
    std::array<double, 3> endPoint{};
    std::array<double, 3> location{};
    std::array<double, 3> pickPoint{};
    bool hasPickPoint = false;
    bool hasArea = false;
    bool hasCentroid = false;
    bool hasNormal = false;
    bool hasLength = false;
    bool hasStartEnd = false;
    bool hasLocation = false;
};

struct DistanceResult
{
    bool success = false;
    bool cancelled = false;
    std::string error;
    std::array<double, 3> point1{};
    std::array<double, 3> point2{};
    double distance = 0.0;
    std::array<double, 3> vector{};
};

// ─── Prompt Busy Guard ───────────────────────────────────────────────
// C8 fix: Only one modal prompt can be active at a time. A second HTTP
// request attempting a concurrent prompt will receive an immediate error
// instead of colliding with the active GetPoint/GetObject modal loop.

bool IsPromptActive();

// ─── Prompt Functions ───────────────────────────────────────────────
// Each function blocks the calling (HTTP) thread until the user responds
// or the timeout expires. The modal GetPoint/GetObject runs on the main
// thread via Dispatch + condition_variable.

PointResult PromptForPoint(const std::string& message,
                           const double* basePoint,      // nullptr or xyz[3]
                           const std::string& constrainToObjectId,
                           int timeoutSeconds = 60);

ObjectResult PromptForObject(const std::string& message,
                             const std::string& filter,
                             int timeoutSeconds = 60);

MultiObjectResult PromptForObjects(const std::string& message,
                                    const std::string& filter,
                                    int minCount,
                                    int timeoutSeconds = 120);

SubObjectResult PromptForSubObject(const std::string& message,
                                    const std::string& subFilter,
                                    int timeoutSeconds = 60);

DistanceResult PromptForDistance(const std::string& message1,
                                 const std::string& message2,
                                 int timeoutSeconds = 120);

} // namespace Rook
