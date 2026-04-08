// SceneGraphConduit.h
//
// CRhinoDisplayConduit subclass that draws the scene graph overlay:
// - Colored relationship lines between object centroids (PostDrawObjects)
// - Floating classification labels above objects (DrawOverlay / DrawForeground)
//
// Reads from the immutable snapshot — lock-free.
// Rebuilds draw data only when the snapshot sequence changes (throttled 500ms).

#pragma once

#include "SceneGraph/SceneGraphModels.h"
#include <vector>
#include <mutex>
#include <atomic>

namespace Rook {

class CSceneGraphConduit : public CRhinoDisplayConduit
{
public:
    CSceneGraphConduit();

    // ─── Enable / Disable (must be called on main thread) ────
    void Enable();
    void Disable();
    void RefreshSnapshot();

    bool IsActive() const { return m_enabled.load(); }

    // ─── Display settings ────────────────────────────────────
    bool ShowLabels = true;
    bool ShowEdges = true;
    int LineThickness = 2;
    int LabelFontHeight = 12;

protected:
    // CRhinoDisplayConduit override
    bool ExecConduit(CRhinoDisplayPipeline& dp, UINT channel, bool& terminate) override;

private:
    // ─── Draw data structs ───────────────────────────────────
    struct EdgeDrawData {
        ON_3dPoint from;
        ON_3dPoint to;
        ON_3dPoint midpoint;
        ON_Color color;
    };

    struct LabelDrawData {
        ON_3dPoint position;
        ON_wString text;
        ON_Color color;
    };

    void RebuildDrawData();

    // ─── Color lookup helpers ────────────────────────────────
    static ON_Color RelationshipColor(const std::string& rel);
    static ON_Color ClassColor(const std::string& shapeClass);

    // ─── Draw data (rebuilt when sequence changes) ───────────
    // Protected by m_drawMutex since ExecConduit (main thread)
    // and RebuildDrawData may run from different call sites.
    std::mutex m_drawMutex;
    std::vector<EdgeDrawData> m_edgeDrawData;
    std::vector<LabelDrawData> m_labelDrawData;
    int m_lastDrawSequence = -1;
    DWORD m_lastRefreshTick = 0;
    std::atomic<bool> m_enabled{false};
};

} // namespace Rook
