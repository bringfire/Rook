// GumballContext.h
//
// Plain-data structs for AI Gumball v2 context engine.
// No Rhino SDK pointers — safe to pass across thread boundaries.
//
// These structs are built on the main thread by CGumballManager::BuildContext()
// and serialized to JSON on HTTP worker threads. The full GumballContext is
// returned by GET /gumball/context, giving the AI a complete picture of the
// gumball state + selected objects + spatial neighbors in one round-trip.

#pragma once

#include <string>
#include <vector>
#include <array>

namespace Rook {

// ─── Alignment Mode ───────────────────────────────────────────────

enum class AlignmentMode
{
    World,      // Axes aligned to world XYZ
    CPlane,     // Axes aligned to active construction plane
    Object      // Axes aligned to object geometry (Brep face normal, curve tangent, etc.)
};

inline const char* AlignmentModeToString(AlignmentMode mode)
{
    switch (mode)
    {
    case AlignmentMode::World:  return "world";
    case AlignmentMode::CPlane: return "cplane";
    case AlignmentMode::Object: return "object";
    default:                    return "world";
    }
}

inline AlignmentMode AlignmentModeFromString(const std::string& s)
{
    if (s == "object") return AlignmentMode::Object;
    if (s == "cplane") return AlignmentMode::CPlane;
    return AlignmentMode::World;
}

// ─── Gumball Frame Snapshot ───────────────────────────────────────
// Captures the current gumball frame axes and origin.

struct GumballFrameSnapshot
{
    std::array<double, 3> origin{};
    std::array<double, 3> xAxis{};
    std::array<double, 3> yAxis{};
    std::array<double, 3> zAxis{};
    std::string alignmentMode;  // "world", "cplane", "object"
};

// ─── Selected Object Summary ──────────────────────────────────────
// Per-object summary included in context. Richer than ObjectSnapshot
// because it includes geometry-type-specific fields relevant to
// gumball operations (e.g., isSolid tells AI extrude is meaningful).

struct SelectedObjectSummary
{
    std::string id;
    std::string type;           // "Brep", "Mesh", "Curve", "SubD", etc.
    std::string name;
    std::string layer;

    // Bounding box
    std::array<double, 3> bboxMin{};
    std::array<double, 3> bboxMax{};

    // Geometry-specific (populated where applicable)
    bool isSolid = false;
    int faceCount = 0;
    int edgeCount = 0;
    int vertexCount = 0;
    double volume = 0;
    double area = 0;
    double length = 0;          // Curves only
    bool isClosed = false;
    int degree = 0;             // Curves only

    // Scene graph classification (if available)
    std::string shapeClass;     // "compact", "elongated", "flat", etc.
};

// ─── Available Operations ─────────────────────────────────────────
// Tells the AI which gumball handles are meaningful for the current
// selection. E.g., extrude only makes sense for Breps with planar faces.

struct AvailableOperations
{
    bool canTranslate = true;
    bool canRotate = true;
    bool canScale = true;
    bool canExtrude = false;    // Only for Breps with planar faces

    // Explicit list of enabled handle identifiers.
    // Matches CRhinoGumballAppearance enable/disable granularity.
    std::vector<std::string> enabledHandles;
};

// ─── Spatial Neighbor ─────────────────────────────────────────────
// Nearby objects from the scene graph, giving the AI spatial awareness.

struct SpatialNeighbor
{
    std::string id;
    std::string name;
    std::string type;           // "Brep", "Mesh", etc.
    std::string relationship;   // "adjacent", "supports", "near", "above", etc.
    std::string direction;      // "above", "below", "north", etc.
    double distance = 0;
};

// ─── Full Gumball Context ─────────────────────────────────────────
// Returned by GET /gumball/context. Everything the AI needs to
// understand the current interactive state.

struct GumballContext
{
    // Gumball state
    bool enabled = false;
    bool dragActive = false;
    int dragCount = 0;

    // Frame
    GumballFrameSnapshot frame;

    // Selection
    int objectCount = 0;
    std::vector<SelectedObjectSummary> objects;

    // Operations
    AvailableOperations operations;

    // Spatial context (from scene graph)
    std::vector<SpatialNeighbor> neighbors;

    // Document context
    std::string viewName;
    std::string units;
    double tolerance = 0.01;
};

} // namespace Rook
