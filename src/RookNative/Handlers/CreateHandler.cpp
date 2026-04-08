// CreateHandler.cpp
//
// POST /create — Creates geometry objects by type.
// Supports: POINT, LINE, POLYLINE, CIRCLE, ARC, RECTANGLE,
//           BOX, SPHERE, CYLINDER, CONE, EXTRUDE,
//           INTERPOLATED_CURVE, CONTROL_POINT_CURVE

#include "stdafx.h"
#include "Handlers/CreateHandler.h"
#include "Infrastructure/LayerHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/ObjectDiffTracker.h"
#include "Infrastructure/WriteResult.h"
#include "Models/Snapshots.h"
#include "Models/DocumentHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

static CRhinoDoc* ResolveCreateDocOrThrow(unsigned int docSn, const std::string& typeStr)
{
    if (docSn > 0)
    {
        CRhinoDoc* requestedDoc = CRhinoDoc::FromRuntimeSerialNumber(docSn);
        if (!requestedDoc)
        {
            throw std::runtime_error(
                "Requested document not found for /create: " + std::to_string(docSn));
        }

        return requestedDoc;
    }

    CRhinoDoc* fallbackDoc = ResolveDoc(0);
    return fallbackDoc;
}

// Snapshot a newly created CRhinoObject into an ObjectSnapshot.
// Must be called on the main thread.
static ObjectSnapshot CaptureCreatedObject(const CRhinoObject* obj, CRhinoDoc* pDoc)
{
    ObjectSnapshot snap;
    snap.id = UuidToString(obj->Attributes().m_uuid);
    snap.type = ObjectTypeToString(obj->ObjectType());

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

    return snap;
}

// Apply common attributes (name, layer, color) to object attributes.
static void ApplyCommonAttributes(ON_3dmObjectAttributes& attrs,
                                   const nlohmann::json& body,
                                   CRhinoDoc* pDoc)
{
    if (body.contains("name") && body["name"].is_string())
    {
        attrs.m_name = Utf8ToWide(body["name"].get<std::string>());
    }

    if (body.contains("layer") && body["layer"].is_string())
    {
        std::string layerName = body["layer"].get<std::string>();
        auto ref = Rook::Infrastructure::ResolveLayerRef(pDoc, layerName, "layer");
        attrs.m_layer_index = ref.index;
    }

    if (body.contains("color"))
    {
        try
        {
            ON_Color c = ParseColor(body, "color");
            attrs.m_color = c;
            attrs.SetColorSource(ON::color_from_object);
        }
        catch (...) {}  // silently ignore bad color
    }
}

// Resolve a plane from the "plane" string field (XY, XZ, YZ).
static ON_Plane ResolvePlane(const nlohmann::json& body, const ON_3dPoint& center)
{
    std::string planeStr = body.value("plane", "XY");
    if (IEquals(planeStr, "XZ"))
        return ON_Plane(center, ON_3dVector::XAxis, ON_3dVector::ZAxis);
    if (IEquals(planeStr, "YZ"))
        return ON_Plane(center, ON_3dVector::YAxis, ON_3dVector::ZAxis);
    return ON_Plane(center, ON_3dVector::XAxis, ON_3dVector::YAxis);  // XY default
}

// ─── Type dispatch ──────────────────────────────────────────────────

struct CreateResult {
    ObjectSnapshot snapshot;
};

static CreateResult CreatePoint(const nlohmann::json& body, CRhinoDoc* pDoc,
                                 ON_3dmObjectAttributes& attrs)
{
    ON_3dPoint pt;
    if (body.contains("point"))
        pt = ParsePoint3d(body, "point");
    else if (body.contains("location"))
        pt = ParsePoint3d(body, "location");
    else
        throw std::invalid_argument("POINT requires 'point' or 'location'");

    auto* obj = pDoc->AddPointObject(pt, &attrs);
    if (!obj)
        throw std::runtime_error("Failed to create point object");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateLine(const nlohmann::json& body, CRhinoDoc* pDoc,
                                ON_3dmObjectAttributes& attrs)
{
    ON_3dPoint start = ParsePoint3d(body, "start");
    ON_3dPoint end = ParsePoint3d(body, "end");

    ON_LineCurve line(start, end);
    auto* obj = pDoc->AddCurveObject(line, &attrs);
    if (!obj)
        throw std::runtime_error("Failed to create line object");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreatePolyline(const nlohmann::json& body, CRhinoDoc* pDoc,
                                    ON_3dmObjectAttributes& attrs)
{
    auto points = ParsePointArray(body, "points");
    if (points.size() < 2)
        throw std::invalid_argument("POLYLINE requires at least 2 points");

    ON_Polyline polyline;
    for (const auto& pt : points)
        polyline.Append(pt);

    auto* obj = pDoc->AddCurveObject(polyline, &attrs);
    if (!obj)
        throw std::runtime_error("Failed to create polyline object");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateCircle(const nlohmann::json& body, CRhinoDoc* pDoc,
                                  ON_3dmObjectAttributes& attrs)
{
    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body.value("radius", 0.0);
    if (radius <= 0)
        throw std::invalid_argument("CIRCLE requires a positive radius");

    ON_Plane plane = ResolvePlane(body, center);
    ON_Circle circle(plane, radius);

    auto* obj = pDoc->AddCurveObject(circle, &attrs);
    if (!obj)
        throw std::runtime_error("Failed to create circle object");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateArc(const nlohmann::json& body, CRhinoDoc* pDoc,
                               ON_3dmObjectAttributes& attrs)
{
    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body.value("radius", 0.0);
    if (radius <= 0)
        throw std::invalid_argument("ARC requires a positive radius");

    double startAngleDeg = body.value("startAngle", 0.0);
    double endAngleDeg = body.value("endAngle", 360.0);
    double startRad = startAngleDeg * (ON_PI / 180.0);
    double endRad = endAngleDeg * (ON_PI / 180.0);

    ON_Plane plane = ResolvePlane(body, center);
    ON_Circle circle(plane, radius);
    ON_Arc arc(circle, ON_Interval(startRad, endRad));

    auto* obj = pDoc->AddCurveObject(arc, &attrs);
    if (!obj)
        throw std::runtime_error("Failed to create arc object");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateRectangle(const nlohmann::json& body, CRhinoDoc* pDoc,
                                     ON_3dmObjectAttributes& attrs)
{
    double width = body.value("width", 0.0);
    double height = body.value("height", 0.0);
    if (width <= 0 || height <= 0)
        throw std::invalid_argument("RECTANGLE requires positive width and height");

    ON_3dPoint origin = ParsePoint3dOrDefault(body, "origin",
        ParsePoint3dOrDefault(body, "corner", ON_3dPoint::Origin));

    // Build a closed polyline rectangle
    ON_Polyline rect;
    rect.Append(origin);
    rect.Append(origin + ON_3dVector(width, 0, 0));
    rect.Append(origin + ON_3dVector(width, height, 0));
    rect.Append(origin + ON_3dVector(0, height, 0));
    rect.Append(origin);  // close

    auto* obj = pDoc->AddCurveObject(rect, &attrs);
    if (!obj)
        throw std::runtime_error("Failed to create rectangle object");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateBox(const nlohmann::json& body, CRhinoDoc* pDoc,
                               ON_3dmObjectAttributes& attrs)
{
    // Accept width/depth/height or x/y/z
    double w = body.contains("width") ? body.value("width", 0.0) : body.value("x", 0.0);
    double d = body.contains("depth") ? body.value("depth", 0.0) : body.value("y", 0.0);
    double h = body.contains("height") ? body.value("height", 0.0) : body.value("z", 0.0);
    if (w <= 0 || d <= 0 || h <= 0)
        throw std::invalid_argument("BOX requires positive width, depth, and height");

    ON_3dPoint origin = ParsePoint3dOrDefault(body, "origin",
        ParsePoint3dOrDefault(body, "corner", ON_3dPoint::Origin));

    // ON_BrepBox requires 8 corners in specific order
    ON_3dPoint corners[8];
    corners[0] = origin;
    corners[1] = origin + ON_3dVector(w, 0, 0);
    corners[2] = origin + ON_3dVector(w, d, 0);
    corners[3] = origin + ON_3dVector(0, d, 0);
    corners[4] = origin + ON_3dVector(0, 0, h);
    corners[5] = origin + ON_3dVector(w, 0, h);
    corners[6] = origin + ON_3dVector(w, d, h);
    corners[7] = origin + ON_3dVector(0, d, h);

    ON_Brep* pBrep = ON_BrepBox(corners);
    if (!pBrep)
        throw std::runtime_error("Failed to create box brep");

    auto* obj = pDoc->AddBrepObject(*pBrep, &attrs);
    delete pBrep;
    if (!obj)
        throw std::runtime_error("Failed to add box object to document");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateSphere(const nlohmann::json& body, CRhinoDoc* pDoc,
                                  ON_3dmObjectAttributes& attrs)
{
    ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
    double radius = body.value("radius", 0.0);
    if (radius <= 0)
        throw std::invalid_argument("SPHERE requires a positive radius");

    ON_Sphere sphere(center, radius);
    ON_Brep* pBrep = ON_BrepSphere(sphere);
    if (!pBrep)
        throw std::runtime_error("Failed to create sphere brep");

    auto* obj = pDoc->AddBrepObject(*pBrep, &attrs);
    delete pBrep;
    if (!obj)
        throw std::runtime_error("Failed to add sphere object to document");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateCylinder(const nlohmann::json& body, CRhinoDoc* pDoc,
                                    ON_3dmObjectAttributes& attrs)
{
    double radius = body.value("radius", 0.0);
    double height = body.value("height", 0.0);
    if (radius <= 0 || height == 0)
        throw std::invalid_argument("CYLINDER requires positive radius and non-zero height");

    ON_3dPoint center = ParsePoint3dOrDefault(body, "center",
        ParsePoint3dOrDefault(body, "base", ON_3dPoint::Origin));

    ON_Plane plane(center, ON_3dVector::ZAxis);
    ON_Circle circle(plane, radius);
    ON_Cylinder cylinder(circle, height);

    ON_Brep* pBrep = ON_BrepCylinder(cylinder, true, true);
    if (!pBrep)
        throw std::runtime_error("Failed to create cylinder brep");

    auto* obj = pDoc->AddBrepObject(*pBrep, &attrs);
    delete pBrep;
    if (!obj)
        throw std::runtime_error("Failed to add cylinder object to document");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateCone(const nlohmann::json& body, CRhinoDoc* pDoc,
                                ON_3dmObjectAttributes& attrs)
{
    double radius = body.value("radius", 0.0);
    double height = body.value("height", 0.0);
    if (radius <= 0 || height == 0)
        throw std::invalid_argument("CONE requires positive radius and non-zero height");

    ON_3dPoint center = ParsePoint3dOrDefault(body, "center",
        ParsePoint3dOrDefault(body, "base", ON_3dPoint::Origin));

    // ON_Cone: plane at the base, height to the apex, radius at the base
    ON_Plane plane(center, ON_3dVector::ZAxis);
    ON_Cone cone(plane, height, radius);

    ON_Brep* pBrep = ON_BrepCone(cone, true);
    if (!pBrep)
        throw std::runtime_error("Failed to create cone brep");

    auto* obj = pDoc->AddBrepObject(*pBrep, &attrs);
    delete pBrep;
    if (!obj)
        throw std::runtime_error("Failed to add cone object to document");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateExtrude(const nlohmann::json& body, CRhinoDoc* pDoc,
                                   ON_3dmObjectAttributes& attrs)
{
    ON_UUID curveId = ParseUuid(body, "curveId");
    const CRhinoObject* curveObj = pDoc->LookupObject(curveId);
    if (!curveObj)
        throw std::invalid_argument("Curve not found: " + UuidToString(curveId));

    const ON_Curve* pCurve = ON_Curve::Cast(curveObj->Geometry());
    if (!pCurve)
        throw std::invalid_argument("Object is not a curve");

    // Direction: explicit direction vector, or height along Z
    ON_3dVector direction(0, 0, 0);
    if (body.contains("direction"))
    {
        direction = ParseVector3d(body, "direction");
    }
    else
    {
        double height = body.value("height", 0.0);
        if (height == 0)
            throw std::invalid_argument("EXTRUDE requires 'direction' or non-zero 'height'");
        direction = ON_3dVector(0, 0, height);
    }

    bool cap = body.value("cap", true);

    // Use Rhino's _ExtrudeCrv command for reliable results.
    // Note: RunScript creates its own undo record, which nests inside the caller's
    // UndoScope("Create Object"). A single Undo will revert both the extrusion
    // and the selection, which is the desired behavior.
    // Select the curve by UUID, then run the command.
    unsigned int docRuntimeSn = pDoc->RuntimeSerialNumber();
    std::string curveIdStr = UuidToString(curveId);
    ON_wString wCurveId = Utf8ToWide(curveIdStr);

    // Track objects before command
    ObjectDiffTracker tracker(pDoc);

    // Build the command: select by ID, then extrude with direction
    std::wstring script = L"_-SelId " + std::wstring(static_cast<const wchar_t*>(wCurveId)) +
        L" _-ExtrudeCrv _Solid=" + std::wstring(cap ? L"_Yes" : L"_No") +
        L" " + std::to_wstring(direction.x) + L"," +
        std::to_wstring(direction.y) + L"," +
        std::to_wstring(direction.z) + L"\n";

    RhinoApp().RunScript(docRuntimeSn, script.c_str(), 0);

    auto newObjects = tracker.GetNewObjects();
    if (newObjects.empty())
        throw std::runtime_error("Extrusion command did not create an object");

    // Return the first newly created object
    const CRhinoObject* newObj = pDoc->LookupObject(newObjects[0]);
    if (!newObj)
        throw std::runtime_error("Could not find extruded object");

    return { CaptureCreatedObject(newObj, pDoc) };
}

static CreateResult CreateInterpolatedCurve(const nlohmann::json& body, CRhinoDoc* pDoc,
                                             ON_3dmObjectAttributes& attrs)
{
    auto points = ParsePointArray(body, "points");
    if (points.size() < 2)
        throw std::invalid_argument("INTERPOLATED_CURVE requires at least 2 points");

    int degree = body.value("degree", 3);
    degree = (std::max)(1, (std::min)(degree, 11));

    // Use RhinoInterpCurve for interpolated curve through points
    ON_3dPointArray ptArray;
    for (const auto& pt : points)
        ptArray.Append(pt);

    // RhinoInterpCurve(degree, points, start_tan, end_tan, knot_style)
    // knot_style 0 = uniform, nullptr tangents = natural end conditions
    ON_NurbsCurve* pCurve = RhinoInterpCurve(degree, ptArray, nullptr, nullptr, 0);
    if (!pCurve)
        throw std::runtime_error("Failed to create interpolated curve");

    auto* obj = pDoc->AddCurveObject(*pCurve, &attrs);
    delete pCurve;
    if (!obj)
        throw std::runtime_error("Failed to add interpolated curve to document");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateControlPointCurve(const nlohmann::json& body, CRhinoDoc* pDoc,
                                             ON_3dmObjectAttributes& attrs)
{
    auto points = ParsePointArray(body, "points");
    if (points.size() < 2)
        throw std::invalid_argument("CONTROL_POINT_CURVE requires at least 2 points");

    int degree = body.value("degree", 3);
    int ptCount = static_cast<int>(points.size());
    degree = (std::max)(1, (std::min)(degree, ptCount - 1));

    // Build a clamped uniform NURBS curve with given control points
    ON_NurbsCurve curve(3, false, degree + 1, ptCount);

    // Clamped uniform knot vector
    curve.MakeClampedUniformKnotVector();

    for (int i = 0; i < ptCount; ++i)
        curve.SetCV(i, points[i]);

    auto* obj = pDoc->AddCurveObject(curve, &attrs);
    if (!obj)
        throw std::runtime_error("Failed to add control point curve to document");

    return { CaptureCreatedObject(obj, pDoc) };
}

static CreateResult CreateText(const nlohmann::json& body, CRhinoDoc* pDoc,
                                ON_3dmObjectAttributes& attrs)
{
    std::string text = body.value("text", "");
    if (text.empty())
        throw std::invalid_argument("TEXT requires non-empty 'text'");

    ON_3dPoint point = ParsePoint3dOrDefault(body, "point", ON_3dPoint::Origin);
    double height = body.value("height", 1.0);
    if (!(height > 0.0))
        throw std::invalid_argument("TEXT requires positive 'height'");

    ON_Plane plane = ON_Plane::World_xy;
    plane.origin = point;

    const auto dimContext = pDoc->DimStyleContext();
    const ON_DimStyle parentDimStyle = dimContext.CurrentDimStyle();
    ON_DimStyle dimStyle = parentDimStyle;
    dimStyle.SetTextHeight(height);

    std::string fontName = body.value("font", std::string("Arial"));
    bool bold = body.value("bold", false);
    bool italic = body.value("italic", false);

    ON_Font font;
    if (!font.SetFontCharacteristics(
            Utf8ToWide(fontName),
            bold,
            italic,
            false,
            false))
    {
        font = RhinoApp().AppSettings().DefaultFont();
    }
    dimStyle.SetFont(font);

    ON_Text textObject;
    const ON_wString wideText = Utf8ToWide(text);
    if (!textObject.Create(wideText, &dimStyle, plane))
        throw std::runtime_error("Failed to build text annotation");

    // Persist annotation-level overrides explicitly. Passing an override
    // dimstyle into ON_Text::Create() is not enough by itself for the final
    // object to retain height/font styling.
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

    return { CaptureCreatedObject(textRhinoObject, pDoc) };
}

static CreateResult CreateLinearDimension(const nlohmann::json& body, CRhinoDoc* pDoc,
                                           ON_3dmObjectAttributes& attrs)
{
    ON_3dPoint start = ParsePoint3d(body, "start");
    ON_3dPoint end = ParsePoint3d(body, "end");
    double offset = body.value("offset", 1.0);

    ON_3dVector direction = end - start;
    if (!direction.Unitize())
        throw std::invalid_argument("DIMENSION_LINEAR requires distinct start and end points");

    ON_3dVector perpDir = ON_CrossProduct(direction, ON_3dVector::ZAxis);
    if (!perpDir.Unitize())
    {
        perpDir = ON_CrossProduct(direction, ON_3dVector::YAxis);
        if (!perpDir.Unitize())
            throw std::runtime_error("Failed to construct linear dimension plane");
    }

    const ON_3dPoint mid = start + 0.5 * (end - start);
    const ON_3dPoint offsetPoint = mid + offset * perpDir;
    ON_3dVector planeNormal = ON_CrossProduct(direction, perpDir);
    if (!planeNormal.Unitize())
        planeNormal = ON_3dVector::ZAxis;

    const auto dimContext = pDoc->DimStyleContext();
    auto* obj = pDoc->AddDimLinearObject(
        start,
        end,
        offsetPoint,
        planeNormal,
        &dimContext.CurrentDimStyle(),
        &attrs);
    if (!obj)
        throw std::runtime_error("Failed to create linear dimension");

    return { CaptureCreatedObject(obj, pDoc) };
}

// ─── POST /create ───────────────────────────────────────────────────

void HandleCreate(const httplib::Request& req, httplib::Response& res)
{
    // Parse body on worker thread
    nlohmann::json body;
    unsigned int docSn = 0;

    if (!req.body.empty())
    {
        body = nlohmann::json::parse(req.body, nullptr, false);
        if (body.is_discarded() || !body.is_object())
        {
            CRookServer::SendError(res, "Invalid JSON body");
            return;
        }
    }
    else
    {
        CRookServer::SendError(res, "Request body is required");
        return;
    }

    if (body.contains("documentSerialNumber"))
        docSn = body.value("documentSerialNumber", 0u);

    if (!body.contains("type") || !body["type"].is_string())
    {
        CRookServer::SendError(res, "Missing required field: type");
        return;
    }

    std::string typeStr = body["type"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, typeStr, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveCreateDocOrThrow(docSn, typeStr);
        UndoScope undo(pDoc, L"Create Object");

        ON_3dmObjectAttributes attrs;
        ApplyCommonAttributes(attrs, body, pDoc);

        CreateResult cr;

        if (IEquals(typeStr, "POINT"))
            cr = CreatePoint(body, pDoc, attrs);
        else if (IEquals(typeStr, "TEXT"))
            cr = CreateText(body, pDoc, attrs);
        else if (IEquals(typeStr, "DIMENSION_LINEAR") ||
                 IEquals(typeStr, "DIMENSIONLINEAR") ||
                 IEquals(typeStr, "LINEAR_DIMENSION"))
            cr = CreateLinearDimension(body, pDoc, attrs);
        else if (IEquals(typeStr, "LINE"))
            cr = CreateLine(body, pDoc, attrs);
        else if (IEquals(typeStr, "POLYLINE"))
            cr = CreatePolyline(body, pDoc, attrs);
        else if (IEquals(typeStr, "CIRCLE"))
            cr = CreateCircle(body, pDoc, attrs);
        else if (IEquals(typeStr, "ARC"))
            cr = CreateArc(body, pDoc, attrs);
        else if (IEquals(typeStr, "RECTANGLE"))
            cr = CreateRectangle(body, pDoc, attrs);
        else if (IEquals(typeStr, "BOX"))
            cr = CreateBox(body, pDoc, attrs);
        else if (IEquals(typeStr, "SPHERE"))
            cr = CreateSphere(body, pDoc, attrs);
        else if (IEquals(typeStr, "CYLINDER"))
            cr = CreateCylinder(body, pDoc, attrs);
        else if (IEquals(typeStr, "CONE"))
            cr = CreateCone(body, pDoc, attrs);
        else if (IEquals(typeStr, "EXTRUDE"))
            cr = CreateExtrude(body, pDoc, attrs);
        else if (IEquals(typeStr, "INTERPOLATED_CURVE"))
            cr = CreateInterpolatedCurve(body, pDoc, attrs);
        else if (IEquals(typeStr, "CONTROL_POINT_CURVE"))
            cr = CreateControlPointCurve(body, pDoc, attrs);
        else
            throw std::invalid_argument("Unknown or unsupported geometry type: " + typeStr);

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data = Serializer::SerializeObject(cr.snapshot);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
