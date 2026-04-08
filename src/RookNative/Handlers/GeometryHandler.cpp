// GeometryHandler.cpp
//
// GET /geometry — detailed geometry info for a single object by ID.
// Dispatches via ON_*::Cast() in specificity order (most specific first).

#include "stdafx.h"
#include "Handlers/GeometryHandler.h"
#include "Models/Snapshots.h"
#include "Models/DocumentHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// --- Geometry detail capture (main thread only) ---

static std::string AnnotationTypeToString(ON::AnnotationType annotationType)
{
    switch (annotationType)
    {
    case ON::AnnotationType::Text: return "Text";
    case ON::AnnotationType::Leader: return "Leader";
    case ON::AnnotationType::Aligned: return "AlignedDimension";
    case ON::AnnotationType::Angular: return "AngularDimension";
    case ON::AnnotationType::Angular3pt: return "Angular3ptDimension";
    case ON::AnnotationType::Diameter: return "DiameterDimension";
    case ON::AnnotationType::Radius: return "RadialDimension";
    case ON::AnnotationType::Rotated: return "LinearDimension";
    case ON::AnnotationType::Ordinate: return "OrdinateDimension";
    case ON::AnnotationType::ArcLen: return "ArcLengthDimension";
    case ON::AnnotationType::CenterMark: return "Centermark";
    default: return "Annotation";
    }
}

GeometryDetail CaptureGeometryDetail(const CRhinoObject* obj, const ON_Geometry* geom, const CRhinoDoc* pDoc, std::string& outType)
{
    if (!geom)
    {
        outType = "Unknown";
        return std::monostate{};
    }

    if (pDoc)
    {
        if (const auto* annotation = dynamic_cast<const CRhinoAnnotation*>(obj))
        {
            outType = "Annotation";
            AnnotationDetail d;
            d.annotationType = AnnotationTypeToString(annotation->AnnotationType());
            d.plainText = WideToUtf8(annotation->PlainText());
            d.richText = WideToUtf8(annotation->RichText());

            const ON_DimStyle& dimStyle = annotation->GetEffectiveDimensionStyle(pDoc);
            const ON_Font& font = dimStyle.Font();
            d.fontFamily = WideToUtf8(font.FamilyName());
            d.fontFace = WideToUtf8(font.FaceName());
            d.bold = font.IsBold();
            d.italic = font.IsItalic();
            d.textHeight = RoundTo(dimStyle.TextHeight(), 4);
            return d;
        }
    }

    // --- Point ---
    if (const ON_Point* pt = ON_Point::Cast(geom))
    {
        outType = "Point";
        PointDetail d;
        d.location = { RoundTo(pt->point.x, 4), RoundTo(pt->point.y, 4), RoundTo(pt->point.z, 4) };
        return d;
    }

    // --- PointCloud ---
    if (const ON_PointCloud* cloud = ON_PointCloud::Cast(geom))
    {
        outType = "PointCloud";
        PointCloudDetail d;
        d.pointCount = cloud->PointCount();
        return d;
    }

    // --- Curve subtypes (specific before generic) ---

    if (const ON_LineCurve* line = ON_LineCurve::Cast(geom))
    {
        outType = "LineCurve";
        LineCurveDetail d;
        d.start = { RoundTo(line->PointAtStart().x, 4),
                     RoundTo(line->PointAtStart().y, 4),
                     RoundTo(line->PointAtStart().z, 4) };
        d.end = { RoundTo(line->PointAtEnd().x, 4),
                   RoundTo(line->PointAtEnd().y, 4),
                   RoundTo(line->PointAtEnd().z, 4) };

        double len = 0;
        line->GetLength(&len);
        d.length = RoundTo(len, 4);
        return d;
    }

    if (const ON_ArcCurve* arc = ON_ArcCurve::Cast(geom))
    {
        outType = "ArcCurve";
        ArcCurveDetail d;
        ON_3dPoint center = arc->m_arc.Center();
        d.center = { RoundTo(center.x, 4), RoundTo(center.y, 4), RoundTo(center.z, 4) };
        d.radius = RoundTo(arc->m_arc.Radius(), 4);
        d.angle = RoundTo(arc->m_arc.AngleDegrees(), 2);

        double len = 0;
        arc->GetLength(&len);
        d.length = RoundTo(len, 4);
        d.isClosed = arc->IsClosed();
        d.degree = arc->Degree();
        return d;
    }

    if (const ON_PolylineCurve* polyline = ON_PolylineCurve::Cast(geom))
    {
        outType = "PolylineCurve";
        PolylineCurveDetail d;
        d.pointCount = polyline->PointCount();

        double len = 0;
        polyline->GetLength(&len);
        d.length = RoundTo(len, 4);
        d.isClosed = polyline->IsClosed();
        return d;
    }

    if (const ON_NurbsCurve* nurbs = ON_NurbsCurve::Cast(geom))
    {
        outType = "NurbsCurve";
        NurbsCurveDetail d;

        double len = 0;
        nurbs->GetLength(&len);
        d.length = RoundTo(len, 4);
        d.isClosed = nurbs->IsClosed();
        d.degree = nurbs->Degree();
        d.pointCount = nurbs->CVCount();
        d.domain = { nurbs->Domain().Min(), nurbs->Domain().Max() };

        // Check if it's a circle (IsArc returns arc; full circle when angle == 2*PI)
        ON_Arc arc;
        if (nurbs->IsArc(nullptr, &arc) && std::fabs(arc.AngleRadians() - 2.0 * ON_PI) < 1e-6)
        {
            d.isCircle = true;
            ON_3dPoint center = arc.Center();
            d.center = Point3{
                RoundTo(center.x, 4),
                RoundTo(center.y, 4),
                RoundTo(center.z, 4)
            };
            d.radius = RoundTo(arc.Radius(), 4);
        }

        return d;
    }

    // Generic curve (fallback for curve types not handled above)
    if (const ON_Curve* curve = ON_Curve::Cast(geom))
    {
        outType = "Curve";
        GenericCurveDetail d;

        double len = 0;
        curve->GetLength(&len);
        d.length = RoundTo(len, 4);
        d.isClosed = curve->IsClosed();
        d.degree = curve->Degree();
        d.domain = { curve->Domain().Min(), curve->Domain().Max() };
        return d;
    }

    // --- Brep ---
    if (const ON_Brep* brep = ON_Brep::Cast(geom))
    {
        outType = "Brep";
        BrepDetail d;
        d.faceCount = brep->m_F.Count();
        d.edgeCount = brep->m_E.Count();
        d.vertexCount = brep->m_V.Count();
        d.isSolid = brep->IsSolid();
        d.isManifold = brep->IsManifold();

        if (d.isSolid)
        {
            ON_MassProperties mp;
            if (brep->VolumeMassProperties(mp, true, false, false, false))
            {
                double vol = mp.Volume();
                if (!std::isnan(vol))
                    d.volume = RoundTo(vol, 4);
            }
        }

        {
            ON_MassProperties mp;
            if (brep->AreaMassProperties(mp, true, false, false, false))
            {
                double a = mp.Area();
                if (!std::isnan(a))
                    d.area = RoundTo(a, 4);
            }
        }

        return d;
    }

    // --- Extrusion (check before Surface — ON_Extrusion derives from ON_Surface) ---
    if (const ON_Extrusion* extrusion = ON_Extrusion::Cast(geom))
    {
        outType = "Extrusion";
        ExtrusionDetail d;
        d.isSolid = extrusion->IsSolid();
        d.capCount = extrusion->CapCount();
        return d;
    }

    // --- SubD ---
    if (const ON_SubD* subd = ON_SubD::Cast(geom))
    {
        outType = "SubD";
        SubDDetail d;
        d.vertexCount = subd->VertexCount();
        d.edgeCount = subd->EdgeCount();
        d.faceCount = subd->FaceCount();
        return d;
    }

    // --- Mesh ---
    if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
    {
        outType = "Mesh";
        MeshDetail d;
        d.vertexCount = mesh->VertexCount();
        d.faceCount = mesh->FaceCount();
        d.isClosed = mesh->IsClosed();
        return d;
    }

    // --- Surface (generic, after extrusion) ---
    if (const ON_Surface* surface = ON_Surface::Cast(geom))
    {
        outType = "Surface";
        SurfaceDetail d;
        d.isClosed = surface->IsClosed(0) || surface->IsClosed(1);
        d.domainU = { surface->Domain(0).Min(), surface->Domain(0).Max() };
        d.domainV = { surface->Domain(1).Min(), surface->Domain(1).Max() };
        return d;
    }

    outType = "Unknown";
    return std::monostate{};
}

// --- Attribute capture ---

AttributeSnapshot CaptureAttributes(const ON_3dmObjectAttributes& attrs)
{
    AttributeSnapshot snap;
    snap.name = WideToUtf8(attrs.m_name);

    switch (attrs.ColorSource())
    {
    case ON::color_from_layer:    snap.colorSource = "ColorFromLayer"; break;
    case ON::color_from_object:   snap.colorSource = "ColorFromObject"; break;
    case ON::color_from_parent:   snap.colorSource = "ColorFromParent"; break;
    case ON::color_from_material: snap.colorSource = "ColorFromMaterial"; break;
    default:                      snap.colorSource = "ColorFromLayer"; break;
    }

    snap.layerIndex = attrs.m_layer_index;
    snap.materialIndex = attrs.m_material_index;
    snap.linetypeIndex = attrs.m_linetype_index;

    // User strings — enumerate keys, then look up each value
    ON_ClassArray<ON_wString> keys;
    attrs.GetUserStringKeys(keys);
    for (int i = 0; i < keys.Count(); ++i)
    {
        ON_wString value;
        if (attrs.GetUserString(keys[i], value))
            snap.userStrings[WideToUtf8(keys[i])] = WideToUtf8(value);
    }

    return snap;
}

// --- Handler ---

void HandleGeometry(const httplib::Request& req, httplib::Response& res)
{
    // Parse object ID and documentSerialNumber from query params or body
    std::string idStr;
    unsigned int docSn = 0;

    if (req.has_param("id"))
        idStr = req.get_param_value("id");
    if (req.has_param("documentSerialNumber"))
    {
        try { docSn = static_cast<unsigned int>(std::stoul(req.get_param_value("documentSerialNumber"))); }
        catch (...) {}
    }

    if (idStr.empty() && !req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object())
        {
            if (body.contains("id") && body["id"].is_string())
                idStr = body["id"].get<std::string>();
            if (docSn == 0 && body.contains("documentSerialNumber"))
                docSn = body.value("documentSerialNumber", 0u);
        }
    }

    if (idStr.empty())
    {
        CRookServer::SendError(res, "Object ID required. Provide ?id=<guid> or {\"id\": \"guid\"}");
        return;
    }

    // Parse UUID on worker thread (no SDK needed)
    ON_UUID uuid = ON_UuidFromString(idStr.c_str());
    if (ON_UuidIsNil(uuid))
    {
        CRookServer::SendError(res, "Invalid UUID format: " + idStr);
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [uuid, idStr, docSn]() -> GeometrySnapshot
    {
        // Resolve document (cannot use thread-local g_request_doc_serial across threads)
        CRhinoDoc* pDoc = nullptr;
        if (docSn > 0)
            pDoc = CRhinoDoc::FromRuntimeSerialNumber(docSn);
        if (!pDoc)
            pDoc = GetDocument();
        if (!pDoc)
            throw std::runtime_error("No active document");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj)
            throw std::runtime_error("Object not found: " + idStr);

        GeometrySnapshot snap;

        // Base info
        snap.id = UuidToString(obj->Attributes().m_uuid);
        snap.objectType = ObjectTypeToString(obj->ObjectType());

        int layerIdx = obj->Attributes().m_layer_index;
        if (layerIdx >= 0 && layerIdx < pDoc->m_layer_table.LayerCount())
        {
            ON_wString layerPath;
            pDoc->m_layer_table.GetLayerPathName(layerIdx, layerPath);
            snap.layer = WideToUtf8(layerPath);
        }
        else
        {
            snap.layer = "Default";
        }

        snap.name = WideToUtf8(obj->Attributes().m_name);
        snap.visible = obj->IsVisible();

        ON_BoundingBox bbox = obj->BoundingBox();
        if (bbox.IsValid())
        {
            snap.bbox.min = { RoundTo(bbox.m_min.x, 4), RoundTo(bbox.m_min.y, 4), RoundTo(bbox.m_min.z, 4) };
            snap.bbox.max = { RoundTo(bbox.m_max.x, 4), RoundTo(bbox.m_max.y, 4), RoundTo(bbox.m_max.z, 4) };
        }

        if (obj->Attributes().ColorSource() == ON::color_from_object)
        {
            ON_Color c = obj->Attributes().m_color;
            snap.color = ColorSnapshot{
                static_cast<int>(c.Red()),
                static_cast<int>(c.Green()),
                static_cast<int>(c.Blue())
            };
        }

        // Geometry details
        snap.detail = CaptureGeometryDetail(obj, obj->Geometry(), pDoc, snap.geometryType);

        // Attributes
        snap.attributes = CaptureAttributes(obj->Attributes());

        return snap;
    });

    try
    {
        auto snapshot = future.get();
        CRookServer::SendSuccess(res, Serializer::SerializeGeometryDetailed(snapshot));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
