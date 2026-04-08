// RhinoSerializer.h
//
// Worker-thread-safe conversion of snapshot structs to nlohmann::json.
// Mirrors C# RhinoSerializer.cs — must produce identical JSON.

#pragma once

#include "Models/Snapshots.h"

namespace Rook {
namespace Serializer {

// Object summary (for GET /objects)
nlohmann::json SerializeObject(const ObjectSnapshot& obj);

// Detailed geometry + attributes (for GET /geometry)
nlohmann::json SerializeGeometryDetailed(const GeometrySnapshot& snap);

// Layer (for GET /layers)
nlohmann::json SerializeLayer(const LayerSnapshot& layer);

// Document metadata (for GET /document)
nlohmann::json SerializeDocument(const DocumentSnapshot& doc);

// Primitives (reusable)
nlohmann::json SerializeColor(const ColorSnapshot& color);
nlohmann::json SerializeBBox(const BBoxSnapshot& bbox);
nlohmann::json SerializePoint3(const Point3& pt);

// Geometry detail variant visitor — converts GeometryDetail to JSON.
// Shared between GeometryHandler (/geometry) and BlocksHandler (/block/objects-detailed).
struct GeometryDetailVisitor
{
    nlohmann::json operator()(std::monostate) const { return nlohmann::json::object(); }
    nlohmann::json operator()(const BrepDetail& d) const;
    nlohmann::json operator()(const MeshDetail& d) const;
    nlohmann::json operator()(const LineCurveDetail& d) const;
    nlohmann::json operator()(const PolylineCurveDetail& d) const;
    nlohmann::json operator()(const ArcCurveDetail& d) const;
    nlohmann::json operator()(const NurbsCurveDetail& d) const;
    nlohmann::json operator()(const GenericCurveDetail& d) const;
    nlohmann::json operator()(const SurfaceDetail& d) const;
    nlohmann::json operator()(const ExtrusionDetail& d) const;
    nlohmann::json operator()(const PointDetail& d) const;
    nlohmann::json operator()(const PointCloudDetail& d) const;
    nlohmann::json operator()(const SubDDetail& d) const;
    nlohmann::json operator()(const AnnotationDetail& d) const;
};

} // namespace Serializer
} // namespace Rook
