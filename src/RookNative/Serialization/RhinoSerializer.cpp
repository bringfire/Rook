// RhinoSerializer.cpp
//
// Snapshot → JSON conversion. Runs on worker threads (no Rhino SDK access).

#include "stdafx.h"
#include "Serialization/RhinoSerializer.h"

namespace Rook {
namespace Serializer {

// --- Shared enum-to-wire-string mappings ---

// Canonical mapping — promoted 2026-04-19 from static-in-GeometryHandler.cpp
// per Codex PR #64/#65 review. Four callers at promotion time:
// GeometryHandler::CaptureGeometryDetail, HandleDimLinear, HandleDimAligned,
// HandleDimRadius/HandleDimDiameter (PR-4). Keep strings stable — wire
// contract with agents.
std::string AnnotationTypeToString(ON::AnnotationType annotationType)
{
    switch (annotationType)
    {
    case ON::AnnotationType::Text:       return "Text";
    case ON::AnnotationType::Leader:     return "Leader";
    case ON::AnnotationType::Aligned:    return "AlignedDimension";
    case ON::AnnotationType::Angular:    return "AngularDimension";
    case ON::AnnotationType::Angular3pt: return "Angular3ptDimension";
    case ON::AnnotationType::Diameter:   return "DiameterDimension";
    case ON::AnnotationType::Radius:     return "RadialDimension";
    case ON::AnnotationType::Rotated:    return "LinearDimension";
    case ON::AnnotationType::Ordinate:   return "OrdinateDimension";
    case ON::AnnotationType::ArcLen:     return "ArcLengthDimension";
    case ON::AnnotationType::CenterMark: return "Centermark";
    default:                             return "Annotation";
    }
}

// --- Primitives ---

nlohmann::json SerializeColor(const ColorSnapshot& c)
{
    return { {"r", c.r}, {"g", c.g}, {"b", c.b} };
}

nlohmann::json SerializeBBox(const BBoxSnapshot& b)
{
    return {
        {"min", { b.min[0], b.min[1], b.min[2] }},
        {"max", { b.max[0], b.max[1], b.max[2] }}
    };
}

nlohmann::json SerializePoint3(const Point3& pt)
{
    return { pt.x, pt.y, pt.z };
}

// --- Object summary ---

nlohmann::json SerializeObject(const ObjectSnapshot& obj)
{
    nlohmann::json j;
    j["id"] = obj.id;
    j["type"] = obj.type;
    j["layer"] = obj.layer;
    j["name"] = obj.name.empty() ? nlohmann::json(nullptr) : nlohmann::json(obj.name);
    j["visible"] = obj.visible;
    j["bbox"] = SerializeBBox(obj.bbox);

    if (obj.color.has_value())
        j["color"] = SerializeColor(*obj.color);

    if (!obj.blockName.empty())
    {
        j["blockName"] = obj.blockName;
        j["blockDefinitionId"] = obj.blockDefinitionId;
    }

    return j;
}

// --- Geometry detail visitor (declared in RhinoSerializer.h) ---

nlohmann::json GeometryDetailVisitor::operator()(const BrepDetail& d) const
{
    nlohmann::json j;
    j["type"] = "Brep";
    j["faceCount"] = d.faceCount;
    j["edgeCount"] = d.edgeCount;
    j["vertexCount"] = d.vertexCount;
    j["isSolid"] = d.isSolid;
    j["isManifold"] = d.isManifold;
    if (d.volume.has_value()) j["volume"] = *d.volume;
    if (d.area.has_value()) j["area"] = *d.area;
    return j;
}

nlohmann::json GeometryDetailVisitor::operator()(const MeshDetail& d) const
{
    return {
        {"type", "Mesh"},
        {"vertexCount", d.vertexCount},
        {"faceCount", d.faceCount},
        {"isClosed", d.isClosed}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const LineCurveDetail& d) const
{
    return {
        {"type", "LineCurve"},
        {"start", SerializePoint3(d.start)},
        {"end", SerializePoint3(d.end)},
        {"length", d.length}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const PolylineCurveDetail& d) const
{
    return {
        {"type", "PolylineCurve"},
        {"pointCount", d.pointCount},
        {"length", d.length},
        {"isClosed", d.isClosed}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const ArcCurveDetail& d) const
{
    return {
        {"type", "ArcCurve"},
        {"center", SerializePoint3(d.center)},
        {"radius", d.radius},
        {"angle", d.angle},
        {"length", d.length},
        {"isClosed", d.isClosed},
        {"degree", d.degree}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const NurbsCurveDetail& d) const
{
    nlohmann::json j;
    j["type"] = "NurbsCurve";
    j["length"] = d.length;
    j["isClosed"] = d.isClosed;
    j["degree"] = d.degree;
    j["pointCount"] = d.pointCount;
    j["domain"] = { d.domain[0], d.domain[1] };

    if (d.isCircle)
    {
        j["isCircle"] = true;
        if (d.center.has_value())
            j["center"] = SerializePoint3(*d.center);
        if (d.radius.has_value())
            j["radius"] = *d.radius;
    }

    return j;
}

nlohmann::json GeometryDetailVisitor::operator()(const GenericCurveDetail& d) const
{
    return {
        {"type", "Curve"},
        {"length", d.length},
        {"isClosed", d.isClosed},
        {"degree", d.degree},
        {"domain", { d.domain[0], d.domain[1] }}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const SurfaceDetail& d) const
{
    return {
        {"type", "Surface"},
        {"isClosed", d.isClosed},
        {"domainU", { d.domainU[0], d.domainU[1] }},
        {"domainV", { d.domainV[0], d.domainV[1] }}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const ExtrusionDetail& d) const
{
    return {
        {"type", "Extrusion"},
        {"isSolid", d.isSolid},
        {"capCount", d.capCount}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const PointDetail& d) const
{
    return {
        {"type", "Point"},
        {"location", SerializePoint3(d.location)}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const PointCloudDetail& d) const
{
    return {
        {"type", "PointCloud"},
        {"pointCount", d.pointCount}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const SubDDetail& d) const
{
    return {
        {"type", "SubD"},
        {"vertexCount", d.vertexCount},
        {"edgeCount", d.edgeCount},
        {"faceCount", d.faceCount}
    };
}

nlohmann::json GeometryDetailVisitor::operator()(const AnnotationDetail& d) const
{
    return {
        {"type", "Annotation"},
        {"annotationType", d.annotationType},
        {"plainText", d.plainText},
        {"richText", d.richText},
        {"fontFamily", d.fontFamily},
        {"fontFace", d.fontFace},
        {"bold", d.bold},
        {"italic", d.italic},
        {"textHeight", d.textHeight}
    };
}

// --- Attributes ---

static nlohmann::json SerializeAttributes(const AttributeSnapshot& attrs)
{
    nlohmann::json j;
    j["name"] = attrs.name.empty() ? nlohmann::json(nullptr) : nlohmann::json(attrs.name);
    j["colorSource"] = attrs.colorSource;
    j["layerIndex"] = attrs.layerIndex;
    j["materialIndex"] = attrs.materialIndex;
    j["linetype"] = attrs.linetypeIndex;

    if (!attrs.userStrings.empty())
    {
        nlohmann::json us = nlohmann::json::object();
        for (const auto& [key, val] : attrs.userStrings)
            us[key] = val;
        j["userStrings"] = std::move(us);
    }

    return j;
}

// --- Detailed geometry ---

nlohmann::json SerializeGeometryDetailed(const GeometrySnapshot& snap)
{
    nlohmann::json j;

    // Base object info
    j["id"] = snap.id;
    j["type"] = snap.objectType;
    j["layer"] = snap.layer;
    j["name"] = snap.name.empty() ? nlohmann::json(nullptr) : nlohmann::json(snap.name);
    j["visible"] = snap.visible;
    j["bbox"] = SerializeBBox(snap.bbox);

    if (snap.color.has_value())
        j["color"] = SerializeColor(*snap.color);

    // Geometry details via variant visitor
    j["geometry"] = std::visit(GeometryDetailVisitor{}, snap.detail);

    // Attributes
    j["attributes"] = SerializeAttributes(snap.attributes);

    return j;
}

// --- Layer ---

nlohmann::json SerializeLayer(const LayerSnapshot& layer)
{
    nlohmann::json j;
    j["id"] = layer.id;
    j["index"] = layer.index;
    j["name"] = layer.name;
    j["fullPath"] = layer.fullPath;
    j["color"] = SerializeColor(layer.color);
    j["plotColor"] = SerializeColor(layer.plotColor);
    j["plotWeight"] = layer.plotWeight;
    j["linetype"] = layer.linetypeName;
    j["linetypeIndex"] = layer.linetypeIndex;
    j["material"] = layer.materialName.empty()
        ? nlohmann::json(nullptr)
        : nlohmann::json(layer.materialName);
    j["materialIndex"] = layer.materialIndex;
    j["visible"] = layer.visible;
    j["locked"] = layer.locked;
    j["expanded"] = layer.expanded;
    j["parentId"] = layer.parentId.empty()
        ? nlohmann::json(nullptr)
        : nlohmann::json(layer.parentId);
    j["objectCount"] = layer.objectCount;
    return j;
}

// --- Document ---

nlohmann::json SerializeDocument(const DocumentSnapshot& doc)
{
    return {
        {"documentSerialNumber", doc.documentSerialNumber},
        {"name", doc.name},
        {"path", doc.path},
        {"units", doc.units},
        {"tolerance", doc.tolerance},
        {"angleTolerance", doc.angleTolerance},
        {"objectCount", doc.objectCount},
        {"layerCount", doc.layerCount},
        {"activeLayer", doc.activeLayer},
        {"modified", doc.modified}
    };
}

} // namespace Serializer
} // namespace Rook
