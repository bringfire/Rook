// SceneGraphConduit.cpp
//
// Display conduit that visualizes scene graph relationships and labels.
// Reads from the immutable snapshot (lock-free), rebuilds draw geometry
// only when the snapshot sequence changes (throttled to 500ms).

#include "stdafx.h"
#include "SceneGraph/SceneGraphConduit.h"
#include "SceneGraph/SceneGraph.h"
#include "Models/DocumentHelpers.h"

#include <algorithm>

namespace Rook {

// Refresh throttle: 500ms minimum between draw-data rebuilds
static constexpr DWORD REFRESH_THROTTLE_MS = 500;

// ================================================================
// Construction
// ================================================================

CSceneGraphConduit::CSceneGraphConduit()
    : CRhinoDisplayConduit(CSupportChannels::SC_POSTDRAWOBJECTS |
                           CSupportChannels::SC_DRAWOVERLAY)
{
}

// ================================================================
// Enable / Disable
// ================================================================

void CSceneGraphConduit::Enable()
{
    RebuildDrawData();
    m_enabled.store(true);

    CRhinoDoc* doc = RhinoApp().ActiveDoc();
    if (doc)
    {
        CRhinoDisplayConduit::Enable(doc->RuntimeSerialNumber());
        doc->Redraw();
    }
    else
    {
        CRhinoDisplayConduit::Enable();
    }
}

void CSceneGraphConduit::Disable()
{
    m_enabled.store(false);
    CRhinoDisplayConduit::Disable();

    {
        std::lock_guard<std::mutex> lock(m_drawMutex);
        m_edgeDrawData.clear();
        m_labelDrawData.clear();
        m_lastDrawSequence = -1;
    }

    CRhinoDoc* doc = RhinoApp().ActiveDoc();
    if (doc) doc->Redraw();
}

void CSceneGraphConduit::RefreshSnapshot()
{
    RebuildDrawData();
}

// ================================================================
// Color Lookups
// ================================================================

ON_Color CSceneGraphConduit::RelationshipColor(const std::string& rel)
{
    // ON_Color uses ABGR format internally, but constructor is (R,G,B)
    if (rel == "supports")   return ON_Color(220, 60, 60);     // red
    if (rel == "contains")   return ON_Color(60, 100, 220);    // blue
    if (rel == "adjacent")   return ON_Color(60, 200, 80);     // green
    if (rel == "near")       return ON_Color(220, 200, 40);    // yellow
    if (rel == "intersects") return ON_Color(160, 160, 160);   // gray
    if (rel == "above")      return ON_Color(200, 120, 40);    // orange
    return ON_Color(180, 180, 180);  // default gray
}

ON_Color CSceneGraphConduit::ClassColor(const std::string& shapeClass)
{
    if (shapeClass == "vertical-planar")  return ON_Color(180, 80, 80);   // warm red
    if (shapeClass == "horizontal-slab")  return ON_Color(80, 80, 180);   // cool blue
    if (shapeClass == "thin-vertical")    return ON_Color(80, 160, 80);   // green
    if (shapeClass == "thin-horizontal")  return ON_Color(160, 120, 40);  // brown
    if (shapeClass == "compact")          return ON_Color(140, 140, 140); // gray
    if (shapeClass == "irregular")        return ON_Color(180, 140, 200); // purple
    return ON_Color(180, 180, 180);  // default
}

// ================================================================
// Rebuild Draw Data
// ================================================================

void CSceneGraphConduit::RebuildDrawData()
{
    auto snapshot = CSceneGraph::Instance().ReadSnapshot();
    if (!snapshot) return;

    std::vector<EdgeDrawData> newEdges;
    std::vector<LabelDrawData> newLabels;

    // Build centroid lookup
    std::unordered_map<std::string, ON_3dPoint> centroids;
    centroids.reserve(snapshot->nodes.size());
    for (const auto& [id, node] : snapshot->nodes)
    {
        ON_3dPoint c(
            (node.bboxMin[0] + node.bboxMax[0]) / 2.0,
            (node.bboxMin[1] + node.bboxMax[1]) / 2.0,
            (node.bboxMin[2] + node.bboxMax[2]) / 2.0);
        centroids[id] = c;
    }

    // Edge draw data
    newEdges.reserve(snapshot->edges.size());
    for (const auto& edge : snapshot->edges)
    {
        auto srcIt = centroids.find(edge.sourceId);
        auto tgtIt = centroids.find(edge.targetId);
        if (srcIt == centroids.end() || tgtIt == centroids.end()) continue;

        EdgeDrawData dd;
        dd.from = srcIt->second;
        dd.to = tgtIt->second;
        dd.midpoint = ON_3dPoint(
            (dd.from.x + dd.to.x) / 2.0,
            (dd.from.y + dd.to.y) / 2.0,
            (dd.from.z + dd.to.z) / 2.0);
        dd.color = RelationshipColor(edge.relationship);
        newEdges.push_back(dd);
    }

    // Label draw data
    newLabels.reserve(snapshot->nodes.size());
    for (const auto& [id, node] : snapshot->nodes)
    {
        auto it = centroids.find(id);
        if (it == centroids.end()) continue;

        // Label text: prefer domain label, fall back to shape class
        std::string labelUtf8;
        if (!node.domainLabel.empty())
        {
            labelUtf8 = node.domainLabel;
            // Uppercase
            for (auto& ch : labelUtf8)
                ch = static_cast<char>(toupper(static_cast<unsigned char>(ch)));
        }
        else if (!node.shapeClass.empty())
        {
            labelUtf8 = node.shapeClass;
        }
        else
        {
            labelUtf8 = "?";
        }

        // Name: object name or truncated UUID
        std::string nameUtf8 = !node.name.empty()
            ? node.name
            : id.substr(0, (std::min)(static_cast<size_t>(8), id.size()));

        std::string fullText = labelUtf8 + " \"" + nameUtf8 + "\"";

        LabelDrawData ld;
        ld.position = ON_3dPoint(it->second.x, it->second.y, node.bboxMax[2] + 0.3);
        ld.text = Utf8ToWide(fullText);
        ld.color = ClassColor(node.shapeClass);
        newLabels.push_back(ld);
    }

    // Swap into draw data
    {
        std::lock_guard<std::mutex> lock(m_drawMutex);
        m_edgeDrawData = std::move(newEdges);
        m_labelDrawData = std::move(newLabels);
        m_lastDrawSequence = snapshot->sequence;
        m_lastRefreshTick = ::GetTickCount();
    }
}

// ================================================================
// ExecConduit
// ================================================================

bool CSceneGraphConduit::ExecConduit(
    CRhinoDisplayPipeline& dp, UINT channel, bool& /*terminate*/)
{
    if (!m_enabled.load()) return true;

    if (channel == CSupportChannels::SC_POSTDRAWOBJECTS)
    {
        // Auto-refresh: check if snapshot has changed (throttled).
        // Read throttle vars under the lock to avoid data races with RebuildDrawData.
        bool needsRefresh = false;
        {
            std::lock_guard<std::mutex> lock(m_drawMutex);
            auto snapshot = CSceneGraph::Instance().ReadSnapshot();
            if (snapshot && snapshot->sequence != m_lastDrawSequence)
            {
                DWORD now = ::GetTickCount();
                if (now - m_lastRefreshTick >= REFRESH_THROTTLE_MS)
                    needsRefresh = true;
            }
        }
        if (needsRefresh)
            RebuildDrawData();  // takes m_drawMutex internally

        if (!ShowEdges) return true;

        std::lock_guard<std::mutex> lock(m_drawMutex);
        for (const auto& edge : m_edgeDrawData)
        {
            dp.DrawLine(edge.from, edge.to, edge.color, LineThickness);
            dp.DrawPoint(edge.midpoint, 3, RPS_ROUND_DOT, edge.color);
        }
    }
    else if (channel == CSupportChannels::SC_DRAWOVERLAY)
    {
        if (!ShowLabels) return true;

        std::lock_guard<std::mutex> lock(m_drawMutex);
        for (const auto& label : m_labelDrawData)
        {
            // DrawDot draws a tooltip-style label at a 3D world point.
            // Rhino handles the world-to-screen projection internally.
            dp.DrawDot(label.position,
                       static_cast<const wchar_t*>(label.text),
                       label.color,         // fill color
                       ON_Color(255, 255, 255));  // text color (white)
        }
    }

    return true;
}

} // namespace Rook
