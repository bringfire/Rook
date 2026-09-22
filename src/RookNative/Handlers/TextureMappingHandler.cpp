// TextureMappingHandler.cpp
//
// UV texture mapping: box, planar, cylinder, spherical.
// Box and planar mapping use renderer-independent Rhino mapping channels.
// Cylinder/sphere still use legacy commands pending their own validation.

#include "stdafx.h"
#include "Handlers/TextureMappingHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <cmath>
#include <algorithm>
#include <map>
#include <vector>
#include <limits>

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

static double GetDefaultScale(ON::LengthUnitSystem units)
{
    if (units == ON::LengthUnitSystem::None || units == ON::LengthUnitSystem::CustomUnits)
        throw std::invalid_argument("An explicit scale is required for unitless/custom-unit documents");
    const double scale = ON::UnitScale(ON::LengthUnitSystem::Meters, units);
    if (!std::isfinite(scale) || scale <= 0.0)
        throw std::invalid_argument("Cannot determine mapping scale from document units");
    return scale;
}

static double GetScale(const nlohmann::json& body, CRhinoDoc* pDoc)
{
    if (body.contains("scale"))
    {
        if (!body["scale"].is_number())
            throw std::invalid_argument("scale must be a positive finite number");
        const double scale = body["scale"].get<double>();
        if (!std::isfinite(scale) || scale <= 0.0)
            throw std::invalid_argument("scale must be a positive finite number");
        return scale;
    }
    ON::LengthUnitSystem units = pDoc->Properties().ModelUnitsAndTolerances().m_unit_system.UnitSystem();
    return GetDefaultScale(units);
}

// Analyze brep edges to find dominant XY orientation
static std::pair<ON_3dVector, ON_3dVector> CalculateObjectOrientationXY(const ON_Geometry* geom)
{
    struct EdgeData { ON_3dVector vec; double length; double angle; };
    std::vector<EdgeData> edgeData;
    auto addEdge = [&](const ON_3dPoint& start, const ON_3dPoint& end)
    {
        ON_3dVector v(end.x - start.x, end.y - start.y, 0.0);
        const double length = v.Length();
        if (length <= ON_ZERO_TOLERANCE || !v.Unitize()) return;
        double angle = fmod(atan2(v.y, v.x) * 180.0 / ON_PI + 180.0, 180.0);
        edgeData.push_back({ v, length, angle });
    };

    const ON_Brep* brep = ON_Brep::Cast(geom);
    std::unique_ptr<ON_Brep> brepOwned;

    if (!brep)
    {
        if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
        {
            brepOwned.reset(ext->BrepForm());
            brep = brepOwned.get();
        }
    }

    if (brep)
    {
        for (int i = 0; i < brep->m_E.Count(); ++i)
        {
            const ON_BrepEdge& edge = brep->m_E[i];
            if (!edge.IsValid()) continue;

            ON_Interval domain = edge.Domain();
            ON_3dPoint startPt = edge.PointAt(domain.Min());
            ON_3dPoint endPt = edge.PointAt(domain.Max());

            // Closed/curved edges do not provide a reliable grain direction.
            if (edge.IsLinear()) addEdge(startPt, endPt);
        }
    }
    else if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
    {
        const auto& topology = mesh->Topology();
        auto faceNormal = [&](int index)
        {
            const auto& face = mesh->m_F[index];
            ON_3dVector n = ON_CrossProduct(mesh->Vertex(face.vi[1]) - mesh->Vertex(face.vi[0]),
                                          mesh->Vertex(face.vi[2]) - mesh->Vertex(face.vi[0]));
            n.Unitize();
            return n;
        };
        for (int i = 0; i < topology.m_tope.Count(); ++i)
        {
            const auto& edge = topology.m_tope[i];
            // Ignore triangulation/subdivision edges inside a flat face.
            if (edge.m_topf_count == 2 &&
                fabs(faceNormal(edge.m_topfi[0]) * faceNormal(edge.m_topfi[1])) > 1.0 - 1e-8)
                continue;
            const ON_Line line = topology.TopEdgeLine(i);
            addEdge(line.from, line.to);
        }
    }

    if (edgeData.size() < 2)
        return { ON_3dVector::XAxis, ON_3dVector::YAxis };

    // Group edges by similar angle (within 2 degrees)
    std::map<double, double> angleGroupLengths; // representative angle -> total length
    for (const auto& ed : edgeData)
    {
        bool foundGroup = false;
        for (auto& [groupAngle, totalLen] : angleGroupLengths)
        {
            const double difference = fabs(ed.angle - groupAngle);
            if ((std::min)(difference, 180.0 - difference) < 2.0)
            {
                totalLen += ed.length;
                foundGroup = true;
                break;
            }
        }
        if (!foundGroup)
            angleGroupLengths[ed.angle] = ed.length;
    }

    // Find best angle group
    double bestAngle = 0.0;
    double bestLength = 0.0;
    for (const auto& [angle, totalLen] : angleGroupLengths)
    {
        if (totalLen > bestLength)
        {
            bestLength = totalLen;
            bestAngle = angle;
        }
    }

    double bestRad = bestAngle * ON_PI / 180.0;
    ON_3dVector primary(cos(bestRad), sin(bestRad), 0.0);
    ON_3dVector secondary(-sin(bestRad), cos(bestRad), 0.0);
    primary.Unitize();
    secondary.Unitize();
    return { primary, secondary };
}

struct OrientedBBox {
    ON_Plane plane;
    double xSize, ySize, zSize;
};

static OrientedBBox GetObjectOrientedBoundingBox(const ON_Geometry* geom,
    const ON_Plane* requestedFrame = nullptr)
{
    ON_BoundingBox bbox = geom->BoundingBox();
    ON_Plane plane;
    if (requestedFrame)
        plane = *requestedFrame;
    else
    {
        auto [primary, secondary] = CalculateObjectOrientationXY(geom);
        plane = ON_Plane(bbox.Center(), primary, secondary);
    }

    // Bound the geometry in the chosen frame, not the world bounding box.
    ON_Xform toLocal;
    ON_BoundingBox local;
    if (!bbox.IsValid() || !toLocal.ChangeBasis(ON_Plane::World_xy, plane) ||
        !geom->GetTightBoundingBox(local, false, &toLocal) || !local.IsValid())
        throw std::invalid_argument("Cannot compute object mapping bounds");
    const ON_3dPoint middle = local.Center();
    plane.SetOrigin(plane.PointAt(middle.x, middle.y, middle.z));
    return { plane, local.Max().x - local.Min().x,
             local.Max().y - local.Min().y, local.Max().z - local.Min().z };
}

static std::pair<ON_Plane, std::string> GetMappingPlane(const ON_Geometry* geom, const std::string& mode)
{
    ON_BoundingBox bbox = geom->BoundingBox();
    ON_3dPoint center = bbox.Center();

    if (IEquals(mode, "world_xy"))
        return { ON_Plane(center, ON_3dVector::XAxis, ON_3dVector::YAxis), "world_xy" };
    if (IEquals(mode, "world_yz"))
        return { ON_Plane(center, ON_3dVector::YAxis, ON_3dVector::ZAxis), "world_yz" };
    if (IEquals(mode, "world_zx"))
        return { ON_Plane(center, ON_3dVector::ZAxis, ON_3dVector::XAxis), "world_zx" };

    // auto
    auto [primary, secondary] = CalculateObjectOrientationXY(geom);
    return { ON_Plane(center, primary, secondary), "auto" };
}

static bool ApplyDirectTextureMapping(
    CRhinoDoc* pDoc,
    const CRhinoObject* obj,
    const ON_TextureMapping& mapping,
    int channel)
{
    if (nullptr == pDoc || nullptr == obj)
        return false;

    int mappingIndex = pDoc->m_texture_mapping_table.AddTextureMapping(mapping, false);
    if (mappingIndex < 0)
        return false;

    const CRhinoTextureMapping& tableMapping = pDoc->m_texture_mapping_table[mappingIndex];
    // SDK: this is the Rhino SYSTEM renderer ID, not the active renderer.
    // It is the common mapping channel store used by RhinoCommon as well.
    const ON_UUID pluginId = RhinoApp().RhinoRenderPlugInUUID();

    ON_3dmObjectAttributes attrs = obj->Attributes();
    attrs.m_rendering_attributes.DeleteMappingChannel(pluginId, channel);
    if (!attrs.m_rendering_attributes.AddMappingChannel(pluginId, channel, tableMapping.Id()))
    {
        pDoc->m_texture_mapping_table.DeleteTextureMapping(mappingIndex);
        return false;
    }

    if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs, true))
    {
        pDoc->m_texture_mapping_table.DeleteTextureMapping(mappingIndex);
        return false;
    }

    // Reacquire after a document mutation. Do not overwrite mesh channel-1 UVs
    // just to populate a cache for a different requested channel.
    const CRhinoObject* updated = pDoc->LookupObject(attrs.m_uuid);
    if (!updated) return false;
    const auto* stored = updated->Attributes().m_rendering_attributes.MappingChannel(pluginId, channel);
    ON_TextureMapping readback;
    return stored && pDoc->m_texture_mapping_table.GetTextureMapping(stored, readback) &&
        readback.Id() == tableMapping.Id();
}

static std::pair<ON_3dVector, std::string> GetCylinderAxis(
    const ON_Geometry* geom, const std::string& mode,
    const ON_Plane& orientedPlane, double xSize, double ySize, double zSize)
{
    if (IEquals(mode, "x")) return { ON_3dVector::XAxis, "x" };
    if (IEquals(mode, "y")) return { ON_3dVector::YAxis, "y" };
    if (IEquals(mode, "z")) return { ON_3dVector::ZAxis, "z" };

    // auto: pick longest OBB dimension
    if (zSize >= xSize && zSize >= ySize)
        return { ON_3dVector::ZAxis, "auto_z" };
    if (xSize >= ySize)
        return { orientedPlane.xaxis, "auto_primary" };
    return { orientedPlane.yaxis, "auto_secondary" };
}

static ON_Plane CreatePlanePerpendicular(ON_3dPoint origin, ON_3dVector normal)
{
    ON_3dVector xDir;
    if (fabs(normal * ON_3dVector::ZAxis) < 0.99)
        xDir = ON_CrossProduct(ON_3dVector::ZAxis, normal);
    else
        xDir = ON_CrossProduct(ON_3dVector::XAxis, normal);

    if (!xDir.Unitize())
        return ON_Plane(origin, normal);

    ON_3dVector yDir = ON_CrossProduct(normal, xDir);
    if (!yDir.Unitize())
        return ON_Plane(origin, normal);

    return ON_Plane(origin, xDir, yDir);
}

// Legacy command path, retained for cylinder/sphere until those routes migrate.
static bool ApplyMappingViaCommand(CRhinoDoc* pDoc, const CRhinoObject* obj,
    const std::string& mappingType, double scale,
    const ON_Plane& plane, bool capped = true)
{
    // Select only this object
    CRhinoObjectIterator clearIt(*pDoc,
        CRhinoObjectIterator::normal_or_locked_objects,
        CRhinoObjectIterator::active_objects);
    for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
        const_cast<CRhinoObject*>(o)->Select(false);
    const_cast<CRhinoObject*>(obj)->Select(true);

    ON_wString cmd;
    if (mappingType == "box")
        cmd.Format(L"_-ApplyBoxMapping _Enter");
    else if (mappingType == "planar")
        cmd.Format(L"_-ApplyPlanarMapping _Enter");
    else if (mappingType == "cylinder")
        cmd.Format(L"_-ApplyCylindricalMapping %ls _Enter", capped ? L"_Cap=_Yes" : L"_Cap=_No");
    else if (mappingType == "sphere")
        cmd.Format(L"_-ApplySphericalMapping _Enter");
    else
        return false;

    RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), cmd, 0);

    const_cast<CRhinoObject*>(obj)->Select(false);
    return true;
}

// Per-object mapping result
struct MappingResult {
    std::string id;
    bool success;
    std::string name;
    std::string error;
    double xSize = 0, ySize = 0, zSize = 0;
    std::string planeUsed;
    std::string axisUsed;
    double orientationAngle = 0;
};

// ─── POST /material/uv-box ──────────────────────────────────────

// Placement data is independent of a material or renderer. Future mapping
// constructors can reuse this frame/repeat contract without command macros.
static ON_3dVector ReadMappingTriple(const nlohmann::json& value, const char* label)
{
    if (!value.is_array() || value.size() != 3)
        throw std::invalid_argument(std::string(label) + " must contain three finite numbers");
    for (const auto& item : value)
        if (!item.is_number() || !std::isfinite(item.get<double>()))
            throw std::invalid_argument(std::string(label) + " must contain three finite numbers");
    return ON_3dVector(value[0].get<double>(), value[1].get<double>(), value[2].get<double>());
}

void HandleUvBox(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, ids]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        if (body.contains("channel") &&
            (!body["channel"].is_number_integer() || body["channel"].get<double>() < 1.0 ||
             body["channel"].get<double>() > (std::numeric_limits<int>::max)()))
            throw std::invalid_argument("channel must be an integer from 1 to 2147483647");
        const int channel = body.value("channel", 1);
        if (channel <= 0 || channel == ON_ObjectRenderingAttributes::OCSMappingChannelId())
            throw std::invalid_argument("channel must be a positive non-reserved integer");
        if (ids.empty()) throw std::invalid_argument("ids must not be empty");

        const double scale = body.contains("repeat") && !body.contains("scale")
            ? 1.0 : GetScale(body, pDoc);
        ON_3dVector repeat(scale, scale, scale);
        if (body.contains("repeat")) repeat = ReadMappingTriple(body["repeat"], "repeat");
        if (repeat.x <= 0.0 || repeat.y <= 0.0 || repeat.z <= 0.0)
            throw std::invalid_argument("repeat dimensions must be positive");

        ON_Plane explicitFrame = ON_Plane::World_xy;
        bool hasAxes = false, hasOrigin = false;
        if (body.contains("frame"))
        {
            const auto& frame = body["frame"];
            if (!frame.is_object()) throw std::invalid_argument("frame must be an object");
            hasAxes = frame.contains("x_axis") || frame.contains("y_axis");
            if (hasAxes)
            {
                if (!frame.contains("x_axis") || !frame.contains("y_axis"))
                    throw std::invalid_argument("frame requires both x_axis and y_axis");
                ON_3dVector x = ReadMappingTriple(frame["x_axis"], "x_axis");
                ON_3dVector y = ReadMappingTriple(frame["y_axis"], "y_axis");
                if (!x.Unitize() || !y.Unitize() || fabs(x * y) > 1e-8)
                    throw std::invalid_argument("frame axes must be nonzero and perpendicular");
                explicitFrame = ON_Plane(ON_3dPoint::Origin, x, y);
            }
            hasOrigin = frame.contains("origin");
            if (hasOrigin)
            {
                const auto o = ReadMappingTriple(frame["origin"], "origin");
                explicitFrame.SetOrigin(ON_3dPoint(o.x, o.y, o.z));
            }
        }

        UndoScope undo(pDoc, L"Apply box mapping");

        int mappedCount = 0;
        nlohmann::json objects = nlohmann::json::array();

        for (const auto& uuid : ids)
        {
            std::string idStr = UuidToString(uuid);
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj) { objects.push_back({{"id", idStr}, {"error", "not found"}}); continue; }

            const ON_Geometry* geom = obj->Geometry();
            if (!geom || (!ON_Brep::Cast(geom) && !ON_Mesh::Cast(geom) && !ON_Extrusion::Cast(geom)))
            {
                objects.push_back({{"id", idStr}, {"error", "unsupported geometry type"}});
                continue;
            }

            ON_wString nameW = obj->Attributes().m_name;
            std::string name = nameW.IsEmpty() ? idStr.substr(0, 8) : WideToUtf8(nameW);
            OrientedBBox obb;
            try { obb = GetObjectOrientedBoundingBox(geom, hasAxes ? &explicitFrame : nullptr); }
            catch (const std::exception& ex)
            {
                objects.push_back({{"id", idStr}, {"error", ex.what()}});
                continue;
            }
            ON_Plane plane = hasAxes ? explicitFrame : obb.plane;
            plane.SetOrigin(hasOrigin ? explicitFrame.origin : obb.plane.origin);
            const double orientAngle = atan2(plane.xaxis.y, plane.xaxis.x) * 180.0 / ON_PI;
            ON_TextureMapping mapping;
            if (!mapping.SetBoxMapping(plane,
                ON_Interval(-repeat.x / 2.0, repeat.x / 2.0),
                ON_Interval(-repeat.y / 2.0, repeat.y / 2.0),
                ON_Interval(-repeat.z / 2.0, repeat.z / 2.0), true) ||
                !ApplyDirectTextureMapping(pDoc, obj, mapping, channel))
            {
                objects.push_back({{"id", idStr}, {"error", "failed to create or verify box mapping"}});
                continue;
            }
            mappedCount++;

            char bboxStr[64], uvStr[64];
            snprintf(bboxStr, sizeof(bboxStr), "%.1f x %.1f x %.1f", obb.xSize, obb.ySize, obb.zSize);
            snprintf(uvStr, sizeof(uvStr), "%.2f x %.2f x %.2f",
                obb.xSize / repeat.x, obb.ySize / repeat.y, obb.zSize / repeat.z);

            objects.push_back({
                {"id", idStr}, {"name", name},
                {"bbox_size", bboxStr}, {"uv_coverage", uvStr},
                {"dimensions", {obb.xSize, obb.ySize, obb.zSize}},
                {"mapping_origin", {plane.origin.x, plane.origin.y, plane.origin.z}},
                {"mapping_x_axis", {plane.xaxis.x, plane.xaxis.y, plane.xaxis.z}},
                {"mapping_y_axis", {plane.yaxis.x, plane.yaxis.y, plane.yaxis.z}},
                {"orientation_source", hasAxes ? "explicit" : "auto_xy"},
                {"orientation_angle", std::round(orientAngle * 10.0) / 10.0}
            });
        }

        if (mappedCount > 0) pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["mapped_count"] = mappedCount;
        wr.data["scale"] = repeat.x == repeat.y && repeat.x == repeat.z
            ? nlohmann::json(repeat.x) : nlohmann::json(nullptr);
        wr.data["repeat"] = {repeat.x, repeat.y, repeat.z};
        wr.data["channel"] = channel;
        wr.data["objects"] = objects;
        return wr;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /material/uv-planar ───────────────────────────────────

void HandleUvPlanar(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    std::string planeMode = body.value("plane", std::string("auto"));
    int channel = body.value("channel", 1);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, ids, planeMode, channel]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double scale = GetScale(body, pDoc);
        if (scale <= 0)
            throw std::invalid_argument("scale must be positive");

        UndoScope undo(pDoc, L"Apply planar mapping");

        int mappedCount = 0;
        nlohmann::json objects = nlohmann::json::array();

        for (const auto& uuid : ids)
        {
            std::string idStr = UuidToString(uuid);
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj) { objects.push_back({{"id", idStr}, {"error", "not found"}}); continue; }

            const ON_Geometry* geom = obj->Geometry();
            if (!geom || (!ON_Brep::Cast(geom) && !ON_Mesh::Cast(geom) && !ON_Extrusion::Cast(geom)))
            {
                objects.push_back({{"id", idStr}, {"error", "unsupported geometry type"}});
                continue;
            }

            auto [mappingPlane, planeUsed] = GetMappingPlane(geom, planeMode);
            ON_Interval dx(-scale / 2.0, scale / 2.0);
            ON_Interval dy(-scale / 2.0, scale / 2.0);
            ON_Interval dz(-scale / 2.0, scale / 2.0);

            ON_TextureMapping mapping;
            if (!mapping.SetPlaneMapping(mappingPlane, dx, dy, dz))
            {
                objects.push_back({{"id", idStr}, {"error", "failed to create mapping"}});
                continue;
            }

            // Attribute changes may replace the document object; capture output first.
            ON_wString nameW = obj->Attributes().m_name;
            std::string name = nameW.IsEmpty() ? idStr.substr(0, 8) : WideToUtf8(nameW);
            ON_BoundingBox bbox = geom->BoundingBox();
            if (!ApplyDirectTextureMapping(pDoc, obj, mapping, channel))
            {
                objects.push_back({{"id", idStr}, {"error", "failed to apply mapping"}});
                continue;
            }

            mappedCount++;
            ON_3dVector bboxSize = bbox.Max() - bbox.Min();
            char coverageStr[64];
            snprintf(coverageStr, sizeof(coverageStr), "%.2f x %.2f",
                bboxSize.x / scale, bboxSize.y / scale);

            objects.push_back({
                {"id", idStr},
                {"name", name},
                {"plane_used", planeUsed},
                {"uv_coverage", coverageStr}
            });
        }

        if (mappedCount > 0)
            pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["mapped_count"] = mappedCount;
        wr.data["scale"] = scale;
        wr.data["plane"] = planeMode;
        wr.data["channel"] = channel;
        wr.data["objects"] = objects;
        return wr;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /material/uv-cylinder ─────────────────────────────────

void HandleUvCylinder(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    std::string axisMode = body.value("axis", std::string("auto"));
    bool capped = body.value("capped", true);
    int channel = body.value("channel", 1);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, ids, axisMode, capped, channel]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double scale = GetScale(body, pDoc);
        if (scale <= 0)
            throw std::invalid_argument("scale must be positive");

        UndoScope undo(pDoc, L"Apply cylinder mapping");

        int mappedCount = 0;
        nlohmann::json objects = nlohmann::json::array();

        for (const auto& uuid : ids)
        {
            std::string idStr = UuidToString(uuid);
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj) { objects.push_back({{"id", idStr}, {"error", "not found"}}); continue; }

            const ON_Geometry* geom = obj->Geometry();
            if (!geom || (!ON_Brep::Cast(geom) && !ON_Mesh::Cast(geom) && !ON_Extrusion::Cast(geom)))
            {
                objects.push_back({{"id", idStr}, {"error", "unsupported geometry type"}});
                continue;
            }

            auto obb = GetObjectOrientedBoundingBox(geom);
            auto [cylAxis, axisUsed] = GetCylinderAxis(geom, axisMode,
                obb.plane, obb.xSize, obb.ySize, obb.zSize);

            ON_BoundingBox bbox = geom->BoundingBox();
            ON_3dPoint center = bbox.Center();
            ON_Plane basePlane = CreatePlanePerpendicular(center, cylAxis);

            ApplyMappingViaCommand(pDoc, obj, "cylinder", scale, basePlane, capped);
            mappedCount++;

            ON_3dVector bboxSize = bbox.Max() - bbox.Min();
            ON_wString nameW = obj->Attributes().m_name;
            std::string name = nameW.IsEmpty() ? idStr.substr(0, 8) : WideToUtf8(nameW);

            char bboxStr[64];
            snprintf(bboxStr, sizeof(bboxStr), "%.1f x %.1f x %.1f",
                bboxSize.x, bboxSize.y, bboxSize.z);

            objects.push_back({
                {"id", idStr}, {"name", name},
                {"axis_used", axisUsed}, {"bbox_size", bboxStr}, {"capped", capped}
            });
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["mapped_count"] = mappedCount;
        wr.data["scale"] = scale;
        wr.data["axis"] = axisMode;
        wr.data["capped"] = capped;
        wr.data["channel"] = channel;
        wr.data["objects"] = objects;
        return wr;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /material/uv-sphere ───────────────────────────────────

void HandleUvSphere(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    int channel = body.value("channel", 1);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, ids, channel]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double scale = GetScale(body, pDoc);
        if (scale <= 0)
            throw std::invalid_argument("scale must be positive");

        UndoScope undo(pDoc, L"Apply sphere mapping");

        int mappedCount = 0;
        nlohmann::json objects = nlohmann::json::array();

        for (const auto& uuid : ids)
        {
            std::string idStr = UuidToString(uuid);
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj) { objects.push_back({{"id", idStr}, {"error", "not found"}}); continue; }

            const ON_Geometry* geom = obj->Geometry();
            if (!geom || (!ON_Brep::Cast(geom) && !ON_Mesh::Cast(geom) && !ON_Extrusion::Cast(geom)))
            {
                objects.push_back({{"id", idStr}, {"error", "unsupported geometry type"}});
                continue;
            }

            ON_BoundingBox bbox = geom->BoundingBox();
            ON_3dPoint center = bbox.Center();
            ON_Plane plane(center, ON_3dVector::ZAxis);

            ApplyMappingViaCommand(pDoc, obj, "sphere", scale, plane);
            mappedCount++;

            ON_3dVector bboxSize = bbox.Max() - bbox.Min();
            double maxDim = (std::max)({bboxSize.x, bboxSize.y, bboxSize.z});

            ON_wString nameW = obj->Attributes().m_name;
            std::string name = nameW.IsEmpty() ? idStr.substr(0, 8) : WideToUtf8(nameW);

            char bboxStr[64];
            snprintf(bboxStr, sizeof(bboxStr), "%.1f x %.1f x %.1f",
                bboxSize.x, bboxSize.y, bboxSize.z);

            objects.push_back({
                {"id", idStr}, {"name", name},
                {"bbox_size", bboxStr},
                {"bounding_radius", std::round(maxDim / 2.0 * 10.0) / 10.0}
            });
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["mapped_count"] = mappedCount;
        wr.data["scale"] = scale;
        wr.data["channel"] = channel;
        wr.data["objects"] = objects;
        return wr;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
