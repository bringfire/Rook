// GumballContextBuilder.cpp
//
// Implements CGumballManager::BuildContext() — captures the full gumball
// context on the main thread into a plain-data GumballContext struct.
//
// Also implements SetAlignment(), SetAutoAppearance(), UpdateAppearance().
//
// This file is a separate compilation unit from GumballManager.cpp to
// keep drag logic and context logic cleanly separated.

#include "stdafx.h"
#include "Interactive/GumballManager.h"
#include "Models/DocumentHelpers.h"
#include "SceneGraph/SceneGraph.h"
#include "SceneGraph/SceneGraphModels.h"

namespace Rook {

// ════════════════════════════════════════════════════════════════════
// BuildContext — main thread only
// ════════════════════════════════════════════════════════════════════

// Helper: populate geometry-specific fields on SelectedObjectSummary
static void PopulateGeometryDetails(SelectedObjectSummary& sum, const CRhinoObject* pObj)
{
    const ON_Geometry* pGeo = pObj->Geometry();
    if (!pGeo) return;

    // Brep
    const ON_Brep* pBrep = ON_Brep::Cast(pGeo);
    if (pBrep)
    {
        sum.isSolid = pBrep->IsSolid();
        sum.faceCount = pBrep->m_F.Count();
        sum.edgeCount = pBrep->m_E.Count();
        sum.vertexCount = pBrep->m_V.Count();
        if (pBrep->IsSolid())
        {
            ON_MassProperties mp;
            if (pBrep->VolumeMassProperties(mp, true, false, false, false))
                sum.volume = RoundTo(mp.Volume(), 4);
        }
        ON_MassProperties areaMP;
        if (pBrep->AreaMassProperties(areaMP, true, false, false, false))
            sum.area = RoundTo(areaMP.Area(), 4);
        return;
    }

    // Mesh
    const ON_Mesh* pMesh = ON_Mesh::Cast(pGeo);
    if (pMesh)
    {
        sum.vertexCount = pMesh->VertexCount();
        sum.faceCount = pMesh->FaceCount();
        sum.isClosed = pMesh->IsClosed();
        return;
    }

    // SubD
    const ON_SubD* pSubD = ON_SubD::Cast(pGeo);
    if (pSubD)
    {
        sum.vertexCount = static_cast<int>(pSubD->VertexCount());
        sum.edgeCount = static_cast<int>(pSubD->EdgeCount());
        sum.faceCount = static_cast<int>(pSubD->FaceCount());
        return;
    }

    // Curve
    const ON_Curve* pCurve = ON_Curve::Cast(pGeo);
    if (pCurve)
    {
        double len = 0;
        if (pCurve->GetLength(&len))
            sum.length = RoundTo(len, 4);
        sum.isClosed = pCurve->IsClosed();
        sum.degree = pCurve->Degree();
        return;
    }

    // Extrusion (also has IsSolid)
    const ON_Extrusion* pExtr = ON_Extrusion::Cast(pGeo);
    if (pExtr)
    {
        sum.isSolid = pExtr->IsSolid();
        return;
    }
}

// Helper: determine available operations from the set of selected objects
static AvailableOperations DetermineOperations(
    const std::vector<SelectedObjectSummary>& objects)
{
    AvailableOperations ops;
    ops.canTranslate = true;
    ops.canRotate = true;
    ops.canScale = true;

    // Extrude is available if any selected object is a Brep
    for (const auto& obj : objects)
    {
        if (obj.type == "Brep" && obj.faceCount > 0)
        {
            ops.canExtrude = true;
            break;
        }
    }

    // Build enabled handles list
    ops.enabledHandles.reserve(ops.canExtrude ? 17 : 14);
    ops.enabledHandles.push_back("x_translate");
    ops.enabledHandles.push_back("y_translate");
    ops.enabledHandles.push_back("z_translate");
    ops.enabledHandles.push_back("xy_translate");
    ops.enabledHandles.push_back("yz_translate");
    ops.enabledHandles.push_back("zx_translate");
    ops.enabledHandles.push_back("free_translate");
    ops.enabledHandles.push_back("x_rotate");
    ops.enabledHandles.push_back("y_rotate");
    ops.enabledHandles.push_back("z_rotate");
    ops.enabledHandles.push_back("x_scale");
    ops.enabledHandles.push_back("y_scale");
    ops.enabledHandles.push_back("z_scale");
    ops.enabledHandles.push_back("uniform_scale");

    if (ops.canExtrude)
    {
        ops.enabledHandles.push_back("x_extrude");
        ops.enabledHandles.push_back("y_extrude");
        ops.enabledHandles.push_back("z_extrude");
    }

    return ops;
}

// Helper: gather spatial neighbors from the scene graph
static std::vector<SpatialNeighbor> GatherNeighbors(
    const std::vector<std::string>& selectedIds,
    int maxNeighbors = 8)
{
    std::vector<SpatialNeighbor> neighbors;

    auto snapshot = CSceneGraph::Instance().ReadSnapshot();
    if (!snapshot) return neighbors;

    // Collect edges that reference any selected object
    std::set<std::string> selectedSet(selectedIds.begin(), selectedIds.end());
    std::set<std::string> addedNeighbors;

    for (const auto& id : selectedIds)
    {
        auto edgeIt = snapshot->edgesByNode.find(id);
        if (edgeIt == snapshot->edgesByNode.end()) continue;

        for (const auto& edge : edgeIt->second)
        {
            // The neighbor is the other end of the edge
            const std::string& neighborId =
                (edge.sourceId == id) ? edge.targetId : edge.sourceId;

            // Skip self-references, other selected objects, and duplicates
            if (selectedSet.count(neighborId)) continue;
            if (addedNeighbors.count(neighborId)) continue;

            // Look up the node for type/name
            auto nodeIt = snapshot->nodes.find(neighborId);
            if (nodeIt == snapshot->nodes.end()) continue;

            addedNeighbors.insert(neighborId);

            SpatialNeighbor sn;
            sn.id = neighborId;
            sn.name = nodeIt->second.name;
            sn.type = nodeIt->second.geometryType;
            sn.relationship = edge.relationship;
            sn.direction = edge.direction;
            sn.distance = RoundTo(edge.distance, 4);
            neighbors.push_back(std::move(sn));

            if (static_cast<int>(neighbors.size()) >= maxNeighbors)
                return neighbors;
        }
    }

    return neighbors;
}

GumballContext CGumballManager::BuildContext()
{
    GumballContext ctx;
    ctx.enabled = m_enabled.load();
    ctx.dragActive = m_dragging.load();
    ctx.dragCount = GetDragCount();

    // Frame snapshot from the conduit.
    if (m_conduit)
    {
        const CRhinoGumball& gb = m_conduit->Gumball();
        const CRhinoGumballFrame& frame = gb.m_frame;

        const ON_3dPoint& center = frame.Center();
        ctx.frame.origin = {
            RoundTo(center.x, 4),
            RoundTo(center.y, 4),
            RoundTo(center.z, 4)
        };
        const ON_3dVector& ax = frame.Axis(0);
        const ON_3dVector& ay = frame.Axis(1);
        const ON_3dVector& az = frame.Axis(2);
        ctx.frame.xAxis = {
            RoundTo(ax.x, 6), RoundTo(ax.y, 6), RoundTo(ax.z, 6)
        };
        ctx.frame.yAxis = {
            RoundTo(ay.x, 6), RoundTo(ay.y, 6), RoundTo(ay.z, 6)
        };
        ctx.frame.zAxis = {
            RoundTo(az.x, 6), RoundTo(az.y, 6), RoundTo(az.z, 6)
        };
    }
    ctx.frame.alignmentMode = AlignmentModeToString(m_alignmentMode);

    // Document context
    CRhinoDoc* pDoc = GetDocument();
    if (pDoc)
    {
        const ON_3dmUnitsAndTolerances& ut = pDoc->Properties().ModelUnitsAndTolerances();
        ctx.units = WideToUtf8(ut.m_unit_system.ToString());
        ctx.tolerance = ut.m_absolute_tolerance;

        CRhinoView* pView = RhinoApp().ActiveView();
        if (pView)
            ctx.viewName = WideToUtf8(pView->ActiveViewport().Name());
    }
    // Conduit state logged via RhinoApp().Print() in ShowGumball()

    // Selected objects
    ctx.objectCount = static_cast<int>(m_selectedIds.size());
    std::vector<std::string> selectedIdStrings;
    selectedIdStrings.reserve(m_selectedIds.size());

    // P1-2 fix: Hoist snapshot before loop — one atomic refcount instead of N,
    // and all objects see the same consistent snapshot.
    auto sceneSnapshot = CSceneGraph::Instance().ReadSnapshot();

    if (pDoc)
    {
        for (const auto& uuid : m_selectedIds)
        {
            const CRhinoObject* pObj = pDoc->LookupObject(uuid);
            if (!pObj) continue;

            SelectedObjectSummary sum;
            sum.id = UuidToString(uuid);
            sum.type = ObjectTypeToString(pObj->ObjectType());
            sum.name = WideToUtf8(pObj->Attributes().m_name);

            int layerIdx = pObj->Attributes().m_layer_index;
            if (layerIdx >= 0 && layerIdx < pDoc->m_layer_table.LayerCount())
            {
                ON_wString layerPath;
                pDoc->m_layer_table.GetLayerPathName(layerIdx, layerPath);
                sum.layer = WideToUtf8(layerPath);
            }

            ON_BoundingBox bbox = pObj->BoundingBox();
            if (bbox.IsValid())
            {
                sum.bboxMin = {
                    RoundTo(bbox.m_min.x, 4),
                    RoundTo(bbox.m_min.y, 4),
                    RoundTo(bbox.m_min.z, 4)
                };
                sum.bboxMax = {
                    RoundTo(bbox.m_max.x, 4),
                    RoundTo(bbox.m_max.y, 4),
                    RoundTo(bbox.m_max.z, 4)
                };
            }

            // Geometry details
            PopulateGeometryDetails(sum, pObj);

            // Scene graph shape class (if available)
            if (sceneSnapshot)
            {
                auto nodeIt = sceneSnapshot->nodes.find(sum.id);
                if (nodeIt != sceneSnapshot->nodes.end())
                    sum.shapeClass = nodeIt->second.shapeClass;
            }

            selectedIdStrings.push_back(sum.id);
            ctx.objects.push_back(std::move(sum));
        }
    }

    // Available operations
    ctx.operations = DetermineOperations(ctx.objects);

    // Spatial neighbors
    ctx.neighbors = GatherNeighbors(selectedIdStrings);

    return ctx;
}

// ════════════════════════════════════════════════════════════════════
// Alignment
// ════════════════════════════════════════════════════════════════════

void CGumballManager::SetAlignment(AlignmentMode mode)
{
    m_alignmentMode = mode;
    if (m_enabled.load() && !m_selectedIds.empty())
        ShowGumball();  // Rebuild gumball with new alignment
}

// ════════════════════════════════════════════════════════════════════
// Appearance
// ════════════════════════════════════════════════════════════════════

void CGumballManager::SetAutoAppearance(bool enabled)
{
    m_autoAppearance = enabled;
    if (m_enabled.load())
        UpdateAppearance();
}

void CGumballManager::UpdateAppearance()
{
    if (!m_conduit || !m_conduit->IsEnabled()) return;
    if (m_selectedIds.empty()) return;  // P1-3 fix: nothing to configure

    // CRhinoGumballDisplayConduit has no GetAppearance/SetAppearance.
    // Appearance lives on the CRhinoGumball as m_appearance. We must
    // copy the gumball, modify appearance, and re-set via SetBaseGumball.
    CRhinoGumball gb = m_conduit->BaseGumball();
    CRhinoGumballAppearance& appearance = gb.m_appearance;

    if (!m_autoAppearance)
    {
        // Reset all handles to visible
        appearance.m_bEnableXTranslate = true;
        appearance.m_bEnableYTranslate = true;
        appearance.m_bEnableZTranslate = true;
        appearance.m_bEnableXRotate = true;
        appearance.m_bEnableYRotate = true;
        appearance.m_bEnableZRotate = true;
        appearance.m_bEnableXScale = true;
        appearance.m_bEnableYScale = true;
        appearance.m_bEnableZScale = true;
        m_conduit->SetBaseGumball(gb);
        return;
    }

    // Determine dominant geometry type from selection
    CRhinoDoc* pDoc = GetDocument();
    if (!pDoc) return;

    bool hasCurve = false;
    bool allCurves = true;

    for (const auto& uuid : m_selectedIds)
    {
        const CRhinoObject* pObj = pDoc->LookupObject(uuid);
        if (!pObj) continue;

        ON::object_type ot = pObj->ObjectType();
        if (ot == ON::curve_object)
            hasCurve = true;

        if (ot != ON::curve_object)
            allCurves = false;
    }

    // Default: everything on
    appearance.m_bEnableXTranslate = true;
    appearance.m_bEnableYTranslate = true;
    appearance.m_bEnableZTranslate = true;
    appearance.m_bEnableXRotate = true;
    appearance.m_bEnableYRotate = true;
    appearance.m_bEnableZRotate = true;
    appearance.m_bEnableXScale = true;
    appearance.m_bEnableYScale = true;
    appearance.m_bEnableZScale = true;

    // For pure curve selections, disable scale handles (less useful)
    if (allCurves && hasCurve)
    {
        appearance.m_bEnableXScale = false;
        appearance.m_bEnableYScale = false;
        appearance.m_bEnableZScale = false;
    }

    m_conduit->SetBaseGumball(gb);
}

} // namespace Rook
