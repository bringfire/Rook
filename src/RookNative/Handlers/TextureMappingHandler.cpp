// TextureMappingHandler.cpp
//
// UV texture mapping: box, planar, cylinder, spherical.
// Uses ON_TextureMapping + RunScript _-ApplyBoxMapping etc. as needed.

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

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

static double GetDefaultScale(ON::LengthUnitSystem units)
{
    switch (units)
    {
    case ON::LengthUnitSystem::Millimeters: return 1000.0;
    case ON::LengthUnitSystem::Centimeters: return 100.0;
    case ON::LengthUnitSystem::Meters:      return 1.0;
    case ON::LengthUnitSystem::Inches:      return 39.37;
    case ON::LengthUnitSystem::Feet:        return 3.28;
    case ON::LengthUnitSystem::Yards:       return 0.328;
    default:                                return 1000.0;
    }
}

static double GetScale(const nlohmann::json& body, CRhinoDoc* pDoc)
{
    if (body.contains("scale") && body["scale"].is_number())
        return body["scale"].get<double>();
    ON::LengthUnitSystem units = pDoc->Properties().ModelUnitsAndTolerances().m_unit_system.UnitSystem();
    return GetDefaultScale(units);
}

// Analyze brep edges to find dominant XY orientation
static std::pair<ON_3dVector, ON_3dVector> CalculateObjectOrientationXY(const ON_Geometry* geom)
{
    struct EdgeData { ON_3dVector vec; double length; double angle; };
    std::vector<EdgeData> edgeData;

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

            ON_3dVector edgeVec = endPt - startPt;
            ON_3dVector edgeVecXY(edgeVec.x, edgeVec.y, 0.0);
            double lenXY = edgeVecXY.Length();

            if (lenXY > 0.001)
            {
                edgeVecXY.Unitize();
                double angleDeg = atan2(edgeVecXY.y, edgeVecXY.x) * 180.0 / ON_PI;
                if (angleDeg < 0) angleDeg += 180.0;
                edgeData.push_back({ edgeVecXY, lenXY, angleDeg });
            }
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
            if (fabs(ed.angle - groupAngle) < 2.0)
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

static OrientedBBox GetObjectOrientedBoundingBox(const ON_Geometry* geom)
{
    ON_BoundingBox bbox = geom->BoundingBox();
    auto [primary, secondary] = CalculateObjectOrientationXY(geom);
    ON_3dPoint center = bbox.Center();
    ON_Plane plane(center, primary, secondary);

    // Project corners onto oriented axes
    ON_3dPoint corners[8];
    corners[0] = ON_3dPoint(bbox.Min().x, bbox.Min().y, bbox.Min().z);
    corners[1] = ON_3dPoint(bbox.Max().x, bbox.Min().y, bbox.Min().z);
    corners[2] = ON_3dPoint(bbox.Max().x, bbox.Max().y, bbox.Min().z);
    corners[3] = ON_3dPoint(bbox.Min().x, bbox.Max().y, bbox.Min().z);
    corners[4] = ON_3dPoint(bbox.Min().x, bbox.Min().y, bbox.Max().z);
    corners[5] = ON_3dPoint(bbox.Max().x, bbox.Min().y, bbox.Max().z);
    corners[6] = ON_3dPoint(bbox.Max().x, bbox.Max().y, bbox.Max().z);
    corners[7] = ON_3dPoint(bbox.Min().x, bbox.Max().y, bbox.Max().z);

    double xMin = 1e30, xMax = -1e30;
    double yMin = 1e30, yMax = -1e30;
    double zMin = 1e30, zMax = -1e30;

    for (int i = 0; i < 8; ++i)
    {
        ON_3dVector localVec = corners[i] - center;
        double xp = localVec * primary;
        double yp = localVec * secondary;
        double zp = localVec * ON_3dVector::ZAxis;
        xMin = (std::min)(xMin, xp); xMax = (std::max)(xMax, xp);
        yMin = (std::min)(yMin, yp); yMax = (std::max)(yMax, yp);
        zMin = (std::min)(zMin, zp); zMax = (std::max)(zMax, zp);
    }

    return { plane, xMax - xMin, yMax - yMin, zMax - zMin };
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
    const ON_UUID pluginId = RhinoApp().RhinoRenderPlugInUUID();

    ON_3dmObjectAttributes attrs = obj->Attributes();
    attrs.m_rendering_attributes.DeleteMappingChannel(pluginId, channel);
    if (!attrs.m_rendering_attributes.AddMappingChannel(pluginId, channel, tableMapping.Id()))
        return false;

    if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
        return false;

    const_cast<CRhinoObject*>(obj)->SetTextureCoordinates(mapping, nullptr, true);
    return true;
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

// Apply texture mapping to an object using RunScript
// This is the most reliable approach since CRhinoDoc::ModifyTextureMapping
// may not be available or may have a different signature in C++ SDK.
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

    int channel = body.value("channel", 1);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, ids, channel]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double scale = GetScale(body, pDoc);
        if (scale <= 0)
            throw std::invalid_argument("scale must be positive");

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

            auto obb = GetObjectOrientedBoundingBox(geom);
            double orientAngle = atan2(obb.plane.xaxis.y, obb.plane.xaxis.x) * 180.0 / ON_PI;

            ApplyMappingViaCommand(pDoc, obj, "box", scale, obb.plane);
            mappedCount++;

            ON_wString nameW = obj->Attributes().m_name;
            std::string name = nameW.IsEmpty() ? idStr.substr(0, 8) : WideToUtf8(nameW);

            char bboxStr[64], uvStr[64];
            snprintf(bboxStr, sizeof(bboxStr), "%.1f x %.1f x %.1f", obb.xSize, obb.ySize, obb.zSize);
            snprintf(uvStr, sizeof(uvStr), "%.2f x %.2f x %.2f",
                obb.xSize / scale, obb.ySize / scale, obb.zSize / scale);

            objects.push_back({
                {"id", idStr}, {"name", name},
                {"bbox_size", bboxStr}, {"uv_coverage", uvStr},
                {"orientation_angle", std::round(orientAngle * 10.0) / 10.0}
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

            if (!ApplyDirectTextureMapping(pDoc, obj, mapping, channel))
            {
                objects.push_back({{"id", idStr}, {"error", "failed to apply mapping"}});
                continue;
            }

            mappedCount++;
            ON_wString nameW = obj->Attributes().m_name;
            std::string name = nameW.IsEmpty() ? idStr.substr(0, 8) : WideToUtf8(nameW);
            ON_BoundingBox bbox = geom->BoundingBox();
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
