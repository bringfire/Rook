// RhinoSerializer.h
//
// Worker-thread-safe conversion of snapshot structs to nlohmann::json.
// Mirrors C# RhinoSerializer.cs — must produce identical JSON.

#pragma once

#include <string>
#include "Models/Snapshots.h"

// Note: `ON::AnnotationType` resolves against the OpenNURBS `ON` class
// scope declared in opennurbs_dimension.h — not a namespace, so it cannot
// be forward-declared here. Every translation unit that includes this
// header already pulls the SDK via stdafx.h, so the enum is in scope
// by the time this declaration is parsed.

namespace Rook {
namespace Serializer {

// Canonical wire-format string for an annotation type. Shared between
// GeometryHandler.cpp (GET /geometry response's AnnotationDetail field)
// and AnnotationHandler.cpp (typed /annotation/* route response payloads),
// so both surfaces agree byte-for-byte on the enum→string mapping.
// Unknown / unmapped values return "Annotation".
std::string AnnotationTypeToString(ON::AnnotationType annotationType);

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
