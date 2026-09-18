// Snapshots.h
//
// Plain-data structs that cross the thread boundary.
// Populated on the main thread (inside Dispatch lambdas),
// serialized to JSON on worker threads.
// No Rhino SDK pointers, no ON_wString — just std::string, double, int, bool.

#pragma once

#include <string>
#include <vector>
#include <array>
#include <variant>
#include <optional>
#include <unordered_map>

namespace Rook {

// --- Primitives ---

struct Point3 {
    double x = 0, y = 0, z = 0;
};

struct ColorSnapshot {
    int r = 0, g = 0, b = 0;
};

struct BBoxSnapshot {
    std::array<double, 3> min{};
    std::array<double, 3> max{};
};

// --- Base object (for GET /objects listing) ---

struct ObjectSnapshot {
    std::string id;        // UUID as "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    std::string type;      // "Brep", "Curve", "Mesh", etc. (matches C# ObjectType.ToString())
    std::string layer;     // Full path: "Architecture::Walls"
    std::string name;      // May be empty
    bool visible = true;
    BBoxSnapshot bbox;
    std::optional<ColorSnapshot> color;  // Only set when ColorSource == FromObject
    std::string blockName;           // Non-empty only for InstanceReference (selection only)
    std::string blockDefinitionId;   // Non-empty only for InstanceReference (selection only)
};

// --- Geometry type-specific details (for GET /geometry) ---

struct BrepDetail {
    int faceCount = 0;
    int edgeCount = 0;
    int vertexCount = 0;
    bool isSolid = false;
    bool isManifold = false;
    std::optional<double> volume;  // Only if solid and valid (not NaN)
    std::optional<double> area;    // Only if valid (not NaN)
};

struct MeshDetail {
    int vertexCount = 0;
    int faceCount = 0;
    bool isClosed = false;
};

struct LineCurveDetail {
    Point3 start;
    Point3 end;
    double length = 0;
};

struct PolylineCurveDetail {
    int pointCount = 0;
    double length = 0;
    bool isClosed = false;
};

struct ArcCurveDetail {
    Point3 center;
    double radius = 0;
    double angle = 0;    // Degrees, rounded to 2 decimals
    double length = 0;
    bool isClosed = false;
    int degree = 0;
};

struct NurbsCurveDetail {
    double length = 0;
    bool isClosed = false;
    int degree = 0;
    int pointCount = 0;
    std::array<double, 2> domain{};  // [T0, T1] at full precision
    bool isCircle = false;
    std::optional<Point3> center;    // Set if isCircle
    std::optional<double> radius;    // Set if isCircle
};

struct GenericCurveDetail {
    double length = 0;
    bool isClosed = false;
    int degree = 0;
    std::array<double, 2> domain{};
};

struct SurfaceDetail {
    bool isClosed = false;
    std::array<double, 2> domainU{};
    std::array<double, 2> domainV{};
};

struct ExtrusionDetail {
    bool isSolid = false;
    int capCount = 0;
};

struct PointDetail {
    Point3 location;
};

struct PointCloudDetail {
    int pointCount = 0;
};

struct SubDDetail {
    int vertexCount = 0;
    int edgeCount = 0;
    int faceCount = 0;
};

struct AnnotationDetail {
    std::string annotationType;
    std::string plainText;
    std::string richText;
    std::string fontFamily;
    std::string fontFace;
    bool bold = false;
    bool italic = false;
    double textHeight = 0;
};

// Tagged union of all geometry details.
// std::monostate = unknown/unsupported geometry type.
using GeometryDetail = std::variant<
    std::monostate,
    BrepDetail,
    MeshDetail,
    LineCurveDetail,
    PolylineCurveDetail,
    ArcCurveDetail,
    NurbsCurveDetail,
    GenericCurveDetail,
    SurfaceDetail,
    ExtrusionDetail,
    PointDetail,
    PointCloudDetail,
    SubDDetail,
    AnnotationDetail
>;

// --- Attributes (for detailed /geometry response) ---

struct AttributeSnapshot {
    std::string name;
    std::string colorSource;   // "ColorFromLayer", "ColorFromObject", etc.
    int layerIndex = -1;
    int materialIndex = -1;
    int linetypeIndex = -1;
    std::unordered_map<std::string, std::string> userStrings;
};

// --- Full geometry detail (for GET /geometry) ---

struct GeometrySnapshot {
    // Base object info
    std::string id;
    std::string objectType;    // Same as ObjectSnapshot::type
    std::string layer;
    std::string name;
    bool visible = true;
    BBoxSnapshot bbox;
    std::optional<ColorSnapshot> color;

    // Geometry-specific
    std::string geometryType;  // Specific subclass: "NurbsCurve", "ArcCurve", etc.
    GeometryDetail detail;
    AttributeSnapshot attributes;
};

// --- Layer (for GET /layers) ---

struct LayerSnapshot {
    std::string id;
    int index = 0;
    std::string name;
    std::string fullPath;      // "Parent::Child::Name"
    ColorSnapshot color;
    bool visible = true;
    bool locked = false;
    std::string parentId;      // Empty → serialized as null
    int objectCount = 0;

    // Extended properties (Phase 2)
    ColorSnapshot plotColor;
    double plotWeight = 0.0;       // mm, 0 = default
    int linetypeIndex = -1;        // -1 = Continuous (default)
    std::string linetypeName;      // Resolved name
    int materialIndex = -1;        // -1 = no material
    std::string materialName;      // Resolved name
    bool expanded = true;          // UI tree state
};

// --- Document metadata (for GET /document) ---

struct DocumentSnapshot {
    unsigned int documentSerialNumber = 0;
    std::string name;
    std::string path;
    std::string units;         // "Millimeters", "Meters", etc.
    double tolerance = 0.01;
    double angleTolerance = 1.0;  // Degrees
    int objectCount = 0;
    int layerCount = 0;
    std::string activeLayer;
    bool modified = false;
};

} // namespace Rook
