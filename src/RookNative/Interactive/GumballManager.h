// GumballManager.h
//
// Persistent AI Gumball mode: non-blocking gumball that stays visible
// while the user drags handles. Uses WH_MOUSE thread-level hook (C++
// equivalent of C#'s Rhino.UI.MouseCallback) + CRhinoGumballDisplayConduit
// for rendering and hit-testing.
//
// All state lives on the main thread. HTTP threads only read via mutex.

#pragma once

#include "Interactive/GumballContext.h"
#include <string>
#include <vector>
#include <array>
#include <mutex>
#include <atomic>

namespace Rook {

// ─── Data Models ────────────────────────────────────────────────────

struct GumballDragRecord
{
    int dragIndex = 0;
    std::string handleMode;     // "x_translate", "y_rotate", "z_scale", etc.
    std::array<double, 16> deltaTransform{};
    std::array<double, 16> cumulativeTransform{};
    bool isCopy = false;
    bool isRelocate = false;
    std::string timestamp;
    double dragDurationMs = 0.0;
};

// ─── Gumball Manager ────────────────────────────────────────────────

class CGumballManager
{
public:
    static CGumballManager& Instance();

    // ─── Activation (called from HTTP handlers via Dispatch) ────────
    // These must run on the main thread.

    // Activate gumball mode. If ids is non-empty, select those objects first.
    void Activate(const std::vector<std::string>& ids);
    void Deactivate();

    // ─── State Queries (thread-safe via mutex) ──────────────────────

    bool IsEnabled() const { return m_enabled.load(); }
    bool IsDragActive() const { return m_dragging.load(); }
    int GetDragCount() const;
    std::string GetLastMode() const;
    std::array<double, 16> GetCumulativeTransform() const;
    std::vector<GumballDragRecord> GetHistory(int limit) const;

    // ─── v2: Context Engine (Phase 6A) ───────────────────────────────
    // BuildContext() must run on the main thread (accesses m_conduit,
    // Rhino objects, scene graph). Returns a plain-data struct safe for
    // serialization on any thread.

    GumballContext BuildContext();

    // Alignment: controls how gumball axes orient to the selection.
    void SetAlignment(AlignmentMode mode);
    AlignmentMode GetAlignment() const { return m_alignmentMode; }

    // Appearance: auto-configure handle visibility based on geometry type.
    void SetAutoAppearance(bool enabled);
    void UpdateAppearance();

    // Snappy/smooth dragging: snappy mode enables grid-based snapping.
    void SetSnappy(bool enabled);
    bool IsSnappy() const { return m_snappyDragging.load(); }

    void SetDragStrength(double value) { m_dragStrength.store(value); }
    double GetDragStrength() const { return m_dragStrength.load(); }

    void SetAutoReset(bool enabled) { m_autoReset.store(enabled); }
    bool IsAutoReset() const { return m_autoReset.load(); }

    void SetSnapTranslate(double value) { m_snapTranslate.store(value); }
    double GetSnapTranslate() const { return m_snapTranslate.load(); }

    void SetSnapRotateDeg(double value) { m_snapRotateDeg.store(value); }
    double GetSnapRotateDeg() const { return m_snapRotateDeg.load(); }

    void SetSnapScale(double value) { m_snapScale.store(value); }
    double GetSnapScale() const { return m_snapScale.load(); }

    // Cycle alignment mode (World → Object → CPlane → World).
    AlignmentMode CycleAlignment();

private:
    CGumballManager();
    ~CGumballManager();

    // ─── Mouse Hook ─────────────────────────────────────────────────
    // Thread-level WH_MOUSE hook on Rhino's main thread.
    // Detection only: intercepts WM_LBUTTONDOWN to check for gumball
    // handle clicks. Drag tracking is delegated to CRhinoGumballDragger.

    static LRESULT CALLBACK MouseProc(int nCode, WPARAM wParam, LPARAM lParam);

    // Returns true if a gumball handle was hit and the drag was handled.
    // Called from MouseProc on WM_LBUTTONDOWN. Uses CRhinoGumballDragger
    // (modal CRhinoGetPoint loop) for the actual drag — this gives us
    // proper 3D projection, DynamicDraw, and message consumption.
    bool TryPickAndDrag(POINT screenPt);

    void InstallMouseHook();
    void RemoveMouseHook();

    // ─── Keyboard Hook ──────────────────────────────────────────────
    // Thread-level WH_KEYBOARD hook for F4 alignment cycling.

    static LRESULT CALLBACK KeyboardProc(int nCode, WPARAM wParam, LPARAM lParam);
    void InstallKeyboardHook();
    void RemoveKeyboardHook();

    // ─── Selection Tracking ─────────────────────────────────────────
    // Uses a CRhinoEventWatcher to track selection changes.

    class CSelectionWatcher : public CRhinoEventWatcher
    {
    public:
        explicit CSelectionWatcher(CGumballManager& owner);
        void OnSelectObject(CRhinoDoc& doc, const CRhinoObject& object) override;
        void OnSelectObjects(CRhinoDoc& doc, const ON_SimpleArray<const CRhinoObject*>& objects) override;
        void OnDeselectObject(CRhinoDoc& doc, const CRhinoObject& object) override;
        void OnDeselectObjects(CRhinoDoc& doc, const ON_SimpleArray<const CRhinoObject*>& objects) override;
        void OnDeselectAllObjects(CRhinoDoc& doc, int count) override;
        void OnEndCommand(const CRhinoCommand& command,
                          const CRhinoCommandContext& context,
                          CRhinoCommand::result rc) override;
    private:
        CGumballManager& m_owner;
    };

    void UpdateGumballFromSelection();
    void ShowGumball();
    void HideGumball();

    // ─── Drag History Recording ────────────────────────────────────

    void RecordDrag(const ON_Xform& totalXform,
                    std::chrono::steady_clock::time_point dragStart);

    // ─── Sub-Object Transform ─────────────────────────────────────

    // Apply transform to sub-object selections (faces, edges, vertices).
    // Returns true if sub-objects were present and transformed.
    // Returns false if no sub-objects selected (caller should use whole-object transform).
    bool ApplySubObjectTransform(CRhinoDoc* pDoc, const CRhinoObject* pObj,
                                 const ON_Xform& xform);

    // Extrude selected Brep faces along a direction vector.
    // Returns true if at least one face was extruded.
    bool ApplyExtrudeFaces(CRhinoDoc* pDoc, const CRhinoObject* pObj,
                           const ON_3dVector& direction);

    // ─── Numeric Type-In (double-click handle) ──────────────────────

    // Prompt user for a numeric value via CRhinoGetNumber (command line).
    // Returns true if user entered a number.
    bool PromptForHandleValue(GUMBALL_MODE mode, double& outValue);

    // Build the appropriate ON_Xform for a handle mode + typed value.
    // Uses the current gumball frame's axes and origin.
    ON_Xform BuildHandleTransform(GUMBALL_MODE mode, double value);

    // ─── Helpers ────────────────────────────────────────────────────

    static std::array<double, 16> XformToArray(const ON_Xform& xf);
    static std::string NowIso8601();

    // ─── State ──────────────────────────────────────────────────────

    std::atomic<bool> m_enabled{false};
    std::atomic<bool> m_dragging{false};

    // v2: Alignment and appearance (atomic — safe for HTTP handler reads
    // via GetAlignment() without Dispatch)
    std::atomic<AlignmentMode> m_alignmentMode{AlignmentMode::World};
    std::atomic<bool> m_autoAppearance{true};

    // Hook handles
    HHOOK m_mouseHook = nullptr;
    HHOOK m_keyboardHook = nullptr;

    // Selection watcher
    std::unique_ptr<CSelectionWatcher> m_selectionWatcher;

    // Gumball conduit (main thread only)
    CRhinoGumballDisplayConduit* m_conduit = nullptr;

    // Selected objects (main thread only)
    std::vector<ON_UUID> m_selectedIds;

    // Drag state (main thread only)
    ON_Xform m_cumulativeTransform;
    bool m_inDragger = false;  // True while CRhinoGumballDragger is running
    std::atomic<bool> m_snappyDragging{true};  // Snappy by default (matches Rhino)
    std::atomic<double> m_dragStrength{1.0};
    std::atomic<bool> m_autoReset{false};
    std::atomic<double> m_snapTranslate{1.0};
    std::atomic<double> m_snapRotateDeg{15.0};
    std::atomic<double> m_snapScale{0.1};

    // Double-click detection for relocate mode.
    // Tracked inside TryPickAndDrag — if the same handle is picked
    // twice within GetDoubleClickTime() ms, the second pick triggers
    // relocate instead of transform.
    std::chrono::steady_clock::time_point m_lastPickTime{};
    GUMBALL_MODE m_lastPickedMode = gb_mode_nothing;

    // Stats + history (guarded by m_mutex for HTTP reads)
    mutable std::mutex m_mutex;
    int m_dragCount = 0;
    std::string m_lastMode;
    std::array<double, 16> m_cumulativeXfArray{};
    std::vector<GumballDragRecord> m_dragHistory;
};

} // namespace Rook
