// GumballManager.cpp
//
// Persistent AI Gumball: hybrid WH_MOUSE hook + CRhinoGumballDragger.
//
// Detection: WH_MOUSE thread hook intercepts WM_LBUTTONDOWN on Rhino's
// main thread. PickGumball() hit-tests handles. If a handle is hit, the
// hook eats the message (returns 1) so Rhino doesn't process it.
//
// Drag: CRhinoGumballDragger (extends CRhinoGetPoint) enters a modal
// message pump via DragGumball(). This is the Rhino-native way — same
// mechanism as Rhino's own GumballObject command. The modal loop handles
// 3D projection, DynamicDraw, modifier keys, and consumes all mouse events.

#include "stdafx.h"
#include "Interactive/GumballManager.h"
#include "Interactive/PromptManager.h"  // C9: IsPromptActive() for collision guard
#include "Threading/MainThreadDispatcher.h" // Deferred dispatch from hook callbacks
#include "Models/DocumentHelpers.h"

#include <sstream>
#include <iomanip>
#include <chrono>
#include <set>

namespace Rook {

// C5 fix: Guard against MouseProc firing after singleton destruction.
// Set in the destructor, checked at the top of MouseProc. Prevents
// CGumballManager::Instance() from re-constructing a destroyed Meyers
// singleton during Rhino shutdown (undefined behavior).
static std::atomic<bool> s_gumballDestroying{false};

static bool IsTranslationLikeMode(GUMBALL_MODE mode)
{
    return mode == gb_mode_translatex
        || mode == gb_mode_translatey
        || mode == gb_mode_translatez
        || mode == gb_mode_translatexy
        || mode == gb_mode_translateyz
        || mode == gb_mode_translatezx
        || mode == gb_mode_translatefree
        || mode == gb_mode_extrudex
        || mode == gb_mode_extrudey
        || mode == gb_mode_extrudez;
}

static void ScaleTranslationComponents(ON_Xform& xf, double strength)
{
    if (std::abs(strength - 1.0) <= ON_ZERO_TOLERANCE)
        return;

    xf[0][3] *= strength;
    xf[1][3] *= strength;
    xf[2][3] *= strength;
}

// ════════════════════════════════════════════════════════════════════
// Singleton
// ════════════════════════════════════════════════════════════════════

CGumballManager::CGumballManager()
{
    m_cumulativeTransform = ON_Xform::IdentityTransformation;
    m_cumulativeXfArray.fill(0.0);
    m_cumulativeXfArray[0] = m_cumulativeXfArray[5] = m_cumulativeXfArray[10] = m_cumulativeXfArray[15] = 1.0;
}

CGumballManager::~CGumballManager()
{
    s_gumballDestroying.store(true, std::memory_order_release);
    Deactivate();
}

CGumballManager& CGumballManager::Instance()
{
    static CGumballManager instance;
    return instance;
}

// ════════════════════════════════════════════════════════════════════
// Helpers
// ════════════════════════════════════════════════════════════════════

std::array<double, 16> CGumballManager::XformToArray(const ON_Xform& xf)
{
    std::array<double, 16> arr;
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 4; c++)
            arr[r * 4 + c] = xf[r][c];
    return arr;
}

std::string CGumballManager::NowIso8601()
{
    auto now = std::chrono::system_clock::now();
    auto tt = std::chrono::system_clock::to_time_t(now);
    struct tm utc;
    gmtime_s(&utc, &tt);
    std::ostringstream oss;
    oss << std::put_time(&utc, "%Y-%m-%dT%H:%M:%SZ");
    return oss.str();
}

// ════════════════════════════════════════════════════════════════════
// Activation / Deactivation
// ════════════════════════════════════════════════════════════════════

void CGumballManager::Activate(const std::vector<std::string>& ids)
{
    CRhinoDoc* pDoc = GetDocument();
    if (!pDoc) return;

    // Select specified objects
    if (!ids.empty())
    {
        pDoc->UnselectAll(true);
        for (const auto& idStr : ids)
        {
            ON_UUID uuid = ON_UuidFromString(idStr.c_str());
            const CRhinoObject* pObj = pDoc->LookupObject(uuid);
            if (pObj)
                const_cast<CRhinoObject*>(pObj)->Select(true);
        }
        pDoc->Redraw();
    }

    // C23 fix: If already enabled, reposition gumball to current selection
    // (the new IDs were selected above) instead of silently returning.
    // Reset cumulative state so /gumball/status and /gumball/history
    // reflect the new activation, not stale data from the previous one.
    if (m_enabled.load())
    {
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            m_dragCount = 0;
            m_lastMode.clear();
            m_cumulativeXfArray.fill(0.0);
            m_cumulativeXfArray[0] = m_cumulativeXfArray[5] = m_cumulativeXfArray[10] = m_cumulativeXfArray[15] = 1.0;
            m_dragHistory.clear();
        }
        m_cumulativeTransform = ON_Xform::IdentityTransformation;
        UpdateGumballFromSelection();
        return;
    }
    m_enabled.store(true);

    // Don't pre-create the conduit here. ShowGumball() creates a fresh
    // CRhinoGumballDisplayConduit each time it's called (the conduit
    // self-disables via DisableAndDestroy during ExecConduit if state
    // is inconsistent, so we always need a clean instance).

    // Install selection watcher
    m_selectionWatcher = std::make_unique<CSelectionWatcher>(*this);
    m_selectionWatcher->Register();
    m_selectionWatcher->Enable(true);

    // Install hooks
    InstallMouseHook();
    InstallKeyboardHook();

    // Show gumball on current selection
    UpdateGumballFromSelection();

    // Reset stats
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_dragCount = 0;
        m_lastMode.clear();
        m_cumulativeXfArray.fill(0.0);
        m_cumulativeXfArray[0] = m_cumulativeXfArray[5] = m_cumulativeXfArray[10] = m_cumulativeXfArray[15] = 1.0;
        m_dragHistory.clear();
    }

    m_cumulativeTransform = ON_Xform::IdentityTransformation;
}

void CGumballManager::Deactivate()
{
    if (!m_enabled.load()) return;
    m_enabled.store(false);
    m_dragging.store(false);

    RemoveMouseHook();
    RemoveKeyboardHook();

    // UnRegister() before reset() — otherwise Rhino's global event dispatch
    // list still holds a vtable pointer to the destroyed CRhinoEventWatcher
    // subclass. Matches the existing SessionRecorder::Stop pattern.
    if (m_selectionWatcher)
    {
        m_selectionWatcher->Enable(FALSE);
        m_selectionWatcher->UnRegister();
        m_selectionWatcher.reset();
    }

    HideGumball();

    if (m_conduit)
    {
        delete m_conduit;
        m_conduit = nullptr;
    }

    m_selectedIds.clear();

    CRhinoDoc* pDoc = GetDocument();
    if (pDoc) pDoc->Redraw();
}

// ════════════════════════════════════════════════════════════════════
// Mouse Hook
// ════════════════════════════════════════════════════════════════════

void CGumballManager::InstallMouseHook()
{
    if (m_mouseHook) return;

    HWND hWnd = RhinoApp().MainWnd();
    if (!hWnd) return;

    DWORD threadId = ::GetWindowThreadProcessId(hWnd, nullptr);
    m_mouseHook = ::SetWindowsHookExW(WH_MOUSE, MouseProc, NULL, threadId);
}

void CGumballManager::RemoveMouseHook()
{
    if (m_mouseHook)
    {
        ::UnhookWindowsHookEx(m_mouseHook);
        m_mouseHook = nullptr;
    }
}

// ════════════════════════════════════════════════════════════════════
// Keyboard Hook — F4 alignment cycling
// ════════════════════════════════════════════════════════════════════

void CGumballManager::InstallKeyboardHook()
{
    if (m_keyboardHook) return;

    HWND hWnd = RhinoApp().MainWnd();
    if (!hWnd) return;

    DWORD threadId = ::GetWindowThreadProcessId(hWnd, nullptr);
    m_keyboardHook = ::SetWindowsHookExW(WH_KEYBOARD, KeyboardProc, NULL, threadId);
}

void CGumballManager::RemoveKeyboardHook()
{
    if (m_keyboardHook)
    {
        ::UnhookWindowsHookEx(m_keyboardHook);
        m_keyboardHook = nullptr;
    }
}

LRESULT CALLBACK CGumballManager::KeyboardProc(int nCode, WPARAM wParam, LPARAM lParam)
{
    if (nCode >= 0 && !s_gumballDestroying.load(std::memory_order_acquire)
        && !Rook::IsPromptActive())
    {
        auto& self = CGumballManager::Instance();
        if (self.m_enabled.load() && !self.m_inDragger)
        {
            if (wParam == VK_F4)
            {
                // Don't eat Alt+F4 (window close)
                bool altHeld = (::GetKeyState(VK_MENU) & 0x8000) != 0;
                // Only on initial key-down (bit 31=0 means down, bit 30=0 means was up)
                bool keyDown = !(lParam & (1 << 31));
                bool wasUp = !(lParam & (1 << 30));
                if (!altHeld && keyDown && wasUp)
                {
                    // Defer to main thread message loop — doing substantial
                    // UI work (ShowGumball, redraw) inside a hook callback
                    // is re-entrancy-prone and can cause input latency.
                    CMainThreadDispatcher::Instance().Dispatch([]() {
                        CGumballManager::Instance().CycleAlignment();
                    });
                    return 1;  // Eat the keystroke
                }
            }
        }
    }
    return ::CallNextHookEx(nullptr, nCode, wParam, lParam);
}

LRESULT CALLBACK CGumballManager::MouseProc(int nCode, WPARAM wParam, LPARAM lParam)
{
    // C5 fix: Guard against MouseProc firing after singleton destruction.
    // C9 fix: Skip when a modal prompt (GetPoint/GetObject) is active.
    if (nCode >= 0 && !s_gumballDestroying.load(std::memory_order_acquire)
        && !Rook::IsPromptActive())
    {
        auto& self = CGumballManager::Instance();

        // Skip all processing during CRhinoGumballDragger's modal loop.
        // The dragger pumps its own messages — our hook re-enters for each
        // one, but we must not interfere.
        if (self.m_enabled.load() && !self.m_inDragger)
        {
            // Handle both WM_LBUTTONDOWN and WM_LBUTTONDBLCLK.
            // Windows sends WM_LBUTTONDBLCLK (not WM_LBUTTONDOWN) for the
            // second press of a double-click when the window has CS_DBLCLKS
            // style (Rhino viewports do). Our self-detection timing code in
            // TryPickAndDrag handles double-click logic, so we treat both
            // message types identically.
            if (wParam == WM_LBUTTONDOWN || wParam == WM_LBUTTONDBLCLK)
            {
                auto* pMhs = reinterpret_cast<MOUSEHOOKSTRUCT*>(lParam);
                if (self.TryPickAndDrag(pMhs->pt))
                {
                    // Handle was hit, CRhinoGumballDragger ran the entire
                    // drag to completion (or numeric type-in completed).
                    // Eat the message so Rhino doesn't process it.
                    return 1;
                }
            }
        }
    }

    return ::CallNextHookEx(nullptr, nCode, wParam, lParam);
}

// ════════════════════════════════════════════════════════════════════
// Sub-Object Transform
// ════════════════════════════════════════════════════════════════════
//
// Applies the gumball transform to selected sub-objects (faces, edges,
// vertices) rather than the whole object. Each geometry type has a
// different strategy:
//
//   SubD:  ON_SubD::TransformComponents() — first-class SDK support.
//   Mesh:  Direct vertex manipulation — collect vertices from selected
//          faces/vertices, transform, recompute normals.
//   Brep:  RhinoTransformBrepComponents() — SDK function that transforms
//          selected components and bends adjacent faces to match.
//          Falls back to whole-object transform if it returns false.

bool CGumballManager::ApplySubObjectTransform(
    CRhinoDoc* pDoc, const CRhinoObject* pObj, const ON_Xform& xform)
{
    ON_SimpleArray<ON_COMPONENT_INDEX> subIndices;
    int subCount = pObj->GetSelectedSubObjects(subIndices);
    if (subCount <= 0)
        return false;  // No sub-objects selected — caller uses whole-object transform

    const ON_Geometry* pGeom = pObj->Geometry();
    if (!pGeom) return false;

    CRhinoObjRef objRef(pObj);

    // ── SubD: native TransformComponents ──────────────────────────
    if (const ON_SubD* pSubD = ON_SubD::Cast(pGeom))
    {
        ON_SubD newSubD(*pSubD);  // deep copy
        unsigned int moved = newSubD.TransformComponents(
            xform,
            subIndices.Array(),
            static_cast<size_t>(subIndices.Count()),
            ON_SubDComponentLocation::ControlNet);

        if (moved > 0)
        {
            pDoc->ReplaceObject(objRef, newSubD);
            return true;
        }
        return false;
    }

    // ── Mesh: vertex-level transform ──────────────────────────────
    if (const ON_Mesh* pMesh = ON_Mesh::Cast(pGeom))
    {
        ON_Mesh newMesh(*pMesh);  // deep copy

        // Collect unique vertex indices from selected faces and vertices
        std::set<int> vertexSet;
        for (int i = 0; i < subIndices.Count(); i++)
        {
            ON_COMPONENT_INDEX ci = subIndices[i];
            if (ci.m_type == ON_COMPONENT_INDEX::mesh_vertex
                && ci.m_index >= 0 && ci.m_index < newMesh.m_V.Count())
            {
                vertexSet.insert(ci.m_index);
            }
            else if (ci.m_type == ON_COMPONENT_INDEX::mesh_face
                     && ci.m_index >= 0 && ci.m_index < newMesh.m_F.Count())
            {
                const ON_MeshFace& f = newMesh.m_F[ci.m_index];
                for (int j = 0; j < 4; j++)
                {
                    if (f.vi[j] >= 0 && f.vi[j] < newMesh.m_V.Count())
                        vertexSet.insert(f.vi[j]);
                }
            }
        }

        if (vertexSet.empty()) return false;

        // Transform collected vertices
        for (int vi : vertexSet)
        {
            ON_3dPoint pt = xform * ON_3dPoint(newMesh.m_V[vi]);
            newMesh.m_V[vi] = ON_3fPoint(pt);
        }

        // Also transform double-precision vertices if present
        if (newMesh.HasDoublePrecisionVertices())
        {
            ON_3dPointArray& dv = newMesh.DoublePrecisionVertices();
            for (int vi : vertexSet)
            {
                if (vi < dv.Count())
                    dv[vi] = xform * dv[vi];
            }
        }

        newMesh.InvalidateBoundingBoxes();
        newMesh.ComputeVertexNormals();
        newMesh.ComputeFaceNormals();

        pDoc->ReplaceObject(objRef, newMesh);
        return true;
    }

    // ── Brep: RhinoTransformBrepComponents ──────────────────────────
    // SDK function that transforms selected components, automatically
    // bends/deforms adjacent faces to match, and leaves the rest fixed.
    // This is what Rhino's native _MoveFace command uses internally.
    if (const ON_Brep* pBrep = ON_Brep::Cast(pGeom))
    {
        ON_Brep* pNew = pBrep->Duplicate();
        if (!pNew) return false;

        double tol = pDoc->AbsoluteTolerance();

        // Filter to Brep-relevant component types only
        ON_SimpleArray<ON_COMPONENT_INDEX> brepComponents;
        for (int i = 0; i < subIndices.Count(); i++)
        {
            ON_COMPONENT_INDEX ci = subIndices[i];
            if (ci.m_type == ON_COMPONENT_INDEX::brep_face ||
                ci.m_type == ON_COMPONENT_INDEX::brep_edge ||
                ci.m_type == ON_COMPONENT_INDEX::brep_vertex)
            {
                brepComponents.Append(ci);
            }
        }

        if (brepComponents.Count() == 0) { delete pNew; return false; }

        bool ok = RhinoTransformBrepComponents(
            pNew,
            brepComponents.Count(),
            brepComponents.Array(),
            xform,
            tol,
            10.0,   // time limit in seconds
            true    // use multiple threads
        );

        if (ok)
        {
            pDoc->ReplaceObject(objRef, *pNew);
            delete pNew;
            return true;
        }

        RhinoApp().Print(L"[AIGumball] RhinoTransformBrepComponents failed, "
            L"falling back to whole-object\n");
        delete pNew;
        return false;
    }

    return false;  // Unsupported geometry type — fall back
}

// ════════════════════════════════════════════════════════════════════
// Face Extrusion (Ctrl+drag)
// ════════════════════════════════════════════════════════════════════
//
// Extrudes selected Brep faces along the given direction vector.
// Uses ON_BrepExtrudeFace (opennurbs_brep.h:5440) which modifies a
// Brep in-place: creates side surfaces and an optional cap.
// New faces are appended to brep.m_F[], so existing indices remain
// valid — no reverse-order iteration needed.

bool CGumballManager::ApplyExtrudeFaces(
    CRhinoDoc* pDoc, const CRhinoObject* pObj, const ON_3dVector& direction)
{
    const ON_Brep* pBrep = ON_Brep::Cast(pObj->Geometry());
    if (!pBrep) return false;

    // Collect selected face indices
    ON_SimpleArray<ON_COMPONENT_INDEX> subIndices;
    int subCount = pObj->GetSelectedSubObjects(subIndices);
    if (subCount <= 0) return false;

    std::vector<int> faceIndices;
    for (int i = 0; i < subIndices.Count(); i++)
    {
        if (subIndices[i].m_type == ON_COMPONENT_INDEX::brep_face
            && subIndices[i].m_index >= 0
            && subIndices[i].m_index < pBrep->m_F.Count())
        {
            faceIndices.push_back(subIndices[i].m_index);
        }
    }
    if (faceIndices.empty()) return false;

    // Create extrusion path: line from origin along the direction vector
    ON_LineCurve pathCurve(ON_3dPoint::Origin, ON_3dPoint(direction));

    // Duplicate the Brep and extrude each selected face
    ON_Brep* pNew = pBrep->Duplicate();
    if (!pNew) return false;

    bool anyExtruded = false;
    for (int fi : faceIndices)
    {
        // ON_BrepExtrudeFace returns: 0=fail, 1=success no cap, 2=success+cap
        int result = ON_BrepExtrudeFace(*pNew, fi, pathCurve, true);
        if (result > 0)
            anyExtruded = true;
    }

    if (anyExtruded)
    {
        CRhinoObjRef objRef(pObj);
        pDoc->ReplaceObject(objRef, *pNew);
        delete pNew;
        return true;
    }

    delete pNew;
    return false;
}

// ════════════════════════════════════════════════════════════════════
// Numeric Type-In (double-click handle)
// ════════════════════════════════════════════════════════════════════
//
// When the user double-clicks a gumball handle, we prompt for a numeric
// value via CRhinoGetNumber (Rhino's command line). This matches Rhino's
// native gumball behavior where double-clicking an axis opens a numeric
// input field for precise transforms.

bool CGumballManager::PromptForHandleValue(GUMBALL_MODE mode, double& outValue)
{
    CRhinoGetNumber gn;
    double defaultVal = 0.0;

    switch (mode)
    {
    case gb_mode_translatex: gn.SetCommandPrompt(L"X distance"); break;
    case gb_mode_translatey: gn.SetCommandPrompt(L"Y distance"); break;
    case gb_mode_translatez: gn.SetCommandPrompt(L"Z distance"); break;
    case gb_mode_translatexy: gn.SetCommandPrompt(L"XY distance"); break;
    case gb_mode_translateyz: gn.SetCommandPrompt(L"YZ distance"); break;
    case gb_mode_translatezx: gn.SetCommandPrompt(L"ZX distance"); break;
    case gb_mode_translatefree: gn.SetCommandPrompt(L"Distance"); break;
    case gb_mode_rotatex: gn.SetCommandPrompt(L"X rotation (degrees)"); break;
    case gb_mode_rotatey: gn.SetCommandPrompt(L"Y rotation (degrees)"); break;
    case gb_mode_rotatez: gn.SetCommandPrompt(L"Z rotation (degrees)"); break;
    case gb_mode_scalex:  gn.SetCommandPrompt(L"X scale factor"); defaultVal = 1.0; break;
    case gb_mode_scaley:  gn.SetCommandPrompt(L"Y scale factor"); defaultVal = 1.0; break;
    case gb_mode_scalez:  gn.SetCommandPrompt(L"Z scale factor"); defaultVal = 1.0; break;
    case gb_mode_scalexy: gn.SetCommandPrompt(L"XY scale factor"); defaultVal = 1.0; break;
    case gb_mode_scaleyz: gn.SetCommandPrompt(L"YZ scale factor"); defaultVal = 1.0; break;
    case gb_mode_scalezx: gn.SetCommandPrompt(L"ZX scale factor"); defaultVal = 1.0; break;
    case gb_mode_extrudex: gn.SetCommandPrompt(L"X extrude distance"); break;
    case gb_mode_extrudey: gn.SetCommandPrompt(L"Y extrude distance"); break;
    case gb_mode_extrudez: gn.SetCommandPrompt(L"Z extrude distance"); break;
    default: gn.SetCommandPrompt(L"Value"); break;
    }

    gn.SetDefaultNumber(defaultVal);

    CRhinoGet::result rc = gn.GetNumber();
    if (rc == CRhinoGet::number)
    {
        outValue = gn.Number();
        return true;
    }

    return false;
}

ON_Xform CGumballManager::BuildHandleTransform(GUMBALL_MODE mode, double value)
{
    if (!m_conduit) return ON_Xform::IdentityTransformation;

    const CRhinoGumball& gb = m_conduit->BaseGumball();
    ON_3dPoint center = gb.m_frame.m_plane.origin;
    ON_3dVector xAxis = gb.m_frame.m_plane.xaxis;
    ON_3dVector yAxis = gb.m_frame.m_plane.yaxis;
    ON_3dVector zAxis = gb.m_frame.m_plane.zaxis;

    ON_Xform xf = ON_Xform::IdentityTransformation;

    switch (mode)
    {
    // ── Translation ──
    case gb_mode_translatex:    xf = ON_Xform::TranslationTransformation(xAxis * value); break;
    case gb_mode_translatey:    xf = ON_Xform::TranslationTransformation(yAxis * value); break;
    case gb_mode_translatez:    xf = ON_Xform::TranslationTransformation(zAxis * value); break;
    case gb_mode_translatexy:   xf = ON_Xform::TranslationTransformation((xAxis + yAxis) * value); break;
    case gb_mode_translateyz:   xf = ON_Xform::TranslationTransformation((yAxis + zAxis) * value); break;
    case gb_mode_translatezx:   xf = ON_Xform::TranslationTransformation((zAxis + xAxis) * value); break;
    case gb_mode_translatefree: xf = ON_Xform::TranslationTransformation(zAxis * value); break;

    // ── Rotation (value in degrees) ──
    case gb_mode_rotatex: xf.Rotation(value * ON_PI / 180.0, xAxis, center); break;
    case gb_mode_rotatey: xf.Rotation(value * ON_PI / 180.0, yAxis, center); break;
    case gb_mode_rotatez: xf.Rotation(value * ON_PI / 180.0, zAxis, center); break;

    // ── Scale (value is scale factor, applied along axis from center) ──
    case gb_mode_scalex:
    case gb_mode_scaley:
    case gb_mode_scalez:
    {
        ON_3dVector axis;
        if (mode == gb_mode_scalex) axis = xAxis;
        else if (mode == gb_mode_scaley) axis = yAxis;
        else axis = zAxis;

        // Axis-aligned scale from center: translate to origin, apply
        // rank-1 scale update T = I + (f-1)(a⊗a), translate back.
        ON_Xform toCenter = ON_Xform::TranslationTransformation(-ON_3dVector(center));
        ON_Xform fromCenter = ON_Xform::TranslationTransformation(ON_3dVector(center));
        ON_Xform scl = ON_Xform::IdentityTransformation;
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++)
                scl[i][j] += (value - 1.0) * axis[i] * axis[j];
        xf = fromCenter * scl * toCenter;
        break;
    }
    case gb_mode_scalexy:
    case gb_mode_scaleyz:
    case gb_mode_scalezx:
    {
        // Scale along two axes (plane scale)
        double sx = 1.0, sy = 1.0, sz = 1.0;
        if (mode == gb_mode_scalexy) { sx = value; sy = value; }
        else if (mode == gb_mode_scaleyz) { sy = value; sz = value; }
        else { sz = value; sx = value; }

        // Build in gumball-local space: transform to local, scale, back
        ON_Xform toLocal, fromLocal;
        ON_Plane gbPlane = gb.m_frame.m_plane;
        toLocal.ChangeBasis(ON_Plane::World_xy, gbPlane);
        fromLocal.ChangeBasis(gbPlane, ON_Plane::World_xy);
        ON_Xform scl = ON_Xform::DiagonalTransformation(sx, sy, sz);
        xf = fromLocal * scl * toLocal;
        break;
    }

    // ── Extrude (same transform as translate — extrusion applied separately) ──
    case gb_mode_extrudex: xf = ON_Xform::TranslationTransformation(xAxis * value); break;
    case gb_mode_extrudey: xf = ON_Xform::TranslationTransformation(yAxis * value); break;
    case gb_mode_extrudez: xf = ON_Xform::TranslationTransformation(zAxis * value); break;

    default:
        break;
    }

    return xf;
}

// ════════════════════════════════════════════════════════════════════
// TryPickAndDrag — Rhino-native gumball interaction
// ════════════════════════════════════════════════════════════════════
//
// Called from MouseProc on WM_LBUTTONDOWN. Attempts to pick a gumball
// handle, and if hit, delegates the entire drag to CRhinoGumballDragger.
//
// CRhinoGumballDragger extends CRhinoGetPoint — its DragGumball()
// method enters a modal message pump that:
//   1. Uses Rhino's native 3D projection (no CPlane intersection hacks)
//   2. Calls DynamicDraw() for live preview during drag
//   3. Consumes all mouse events (Rhino doesn't see them)
//   4. Handles shift/ctrl for snapping and relocation
//   5. Returns on mouse-up via GetPoint(nullptr, bOnMouseUp=true)
//
// This is the same mechanism Rhino's own GumballObject command uses
// internally — it's the Rhino-native way to do gumball drags.

bool CGumballManager::TryPickAndDrag(POINT screenPt)
{
    if (m_dragging.load()) return false;
    if (!m_conduit || !m_conduit->IsEnabled()) return false;
    if (!m_conduit->GumballDrawIsEnabled()) return false;
    if (m_selectedIds.empty()) return false;

    CRhinoView* pView = RhinoApp().ActiveView();
    if (!pView) return false;

    // Convert screen → client coordinates for the view window
    POINT clientPt = screenPt;
    ::ScreenToClient(pView->GetSafeHwnd(), &clientPt);

    CRhinoViewport& rhinoVp = pView->ActiveViewport();

    // Build pick context with proper frustum transform.
    CRhinoPickContext pick;
    pick.m_view = pView;

    ON_Line pickLine;
    if (!rhinoVp.VP().GetFrustumLine(clientPt.x, clientPt.y, pickLine))
        return false;
    pick.m_pick_line = pickLine;

    rhinoVp.SetClippingRegionTransformation(clientPt.x, clientPt.y, pick.m_pick_region);

    // Hit-test gumball handles
    if (!m_conduit->PickGumball(pick, nullptr))
        return false;  // Didn't hit any handle

    // ── Handle was hit ──

    m_inDragger = true;  // Prevents hook re-entrancy during modal loops
    auto dragStart = std::chrono::steady_clock::now();

    GUMBALL_MODE pickedMode = m_conduit->m_pick_result.m_gumball_mode;

    // ── Double-click detection → numeric type-in ──
    // Windows sends WM_LBUTTONDOWN before WM_LBUTTONDBLCLK, so we can't
    // rely on the double-click message. Instead, self-detect: if the same
    // handle is picked twice within GetDoubleClickTime() ms, the second
    // pick triggers numeric input. The first pick's drag has near-zero
    // movement (user clicked and released immediately) and is a no-op.
    auto msSinceLastPick = std::chrono::duration_cast<std::chrono::milliseconds>(
        dragStart - m_lastPickTime).count();
    bool isDoubleClick = (msSinceLastPick <= ::GetDoubleClickTime()
                          && m_lastPickedMode == pickedMode
                          && pickedMode != gb_mode_nothing
                          && pickedMode != gb_mode_menu);
    m_lastPickTime = dragStart;
    m_lastPickedMode = pickedMode;

    if (isDoubleClick)
    {
        // ── Numeric type-in: prompt for value, apply transform ──
        // CRhinoGetNumber enters a modal loop (like DragGumball), so
        // m_inDragger stays true to block hook re-entrancy.
        // Also set m_dragging to prevent selection watchers from calling
        // UpdateGumballFromSelection() while the modal prompt is active.
        m_dragging.store(true);
        double value = 0.0;
        if (PromptForHandleValue(pickedMode, value))
        {
            ON_Xform xform = BuildHandleTransform(pickedMode, value);
            if (xform.IsValid() && !xform.IsIdentity())
            {
                CRhinoDoc* pDoc = GetDocument();
                if (pDoc)
                {
                    // Check if this is an extrude handle
                    bool isExtrudeMode = (pickedMode == gb_mode_extrudex
                                          || pickedMode == gb_mode_extrudey
                                          || pickedMode == gb_mode_extrudez);

                    if (isExtrudeMode)
                    {
                        // Extract direction from the handle's axis * value
                        const CRhinoGumball& gb = m_conduit->BaseGumball();
                        ON_3dVector direction;
                        if (pickedMode == gb_mode_extrudex)
                            direction = gb.m_frame.m_plane.xaxis * value;
                        else if (pickedMode == gb_mode_extrudey)
                            direction = gb.m_frame.m_plane.yaxis * value;
                        else
                            direction = gb.m_frame.m_plane.zaxis * value;

                        for (const auto& uuid : m_selectedIds)
                        {
                            const CRhinoObject* pObj = pDoc->LookupObject(uuid);
                            if (!pObj) continue;
                            if (!ApplyExtrudeFaces(pDoc, pObj, direction))
                                pDoc->TransformObject(pObj, xform, true, true, true);
                        }
                    }
                    else
                    {
                        for (const auto& uuid : m_selectedIds)
                        {
                            const CRhinoObject* pObj = pDoc->LookupObject(uuid);
                            if (!pObj) continue;
                            if (!ApplySubObjectTransform(pDoc, pObj, xform))
                                pDoc->TransformObject(pObj, xform, true, true, true);
                        }
                    }

                    RecordDrag(xform, dragStart);
                }
            }
        }

        m_dragging.store(false);
        m_inDragger = false;
        UpdateGumballFromSelection();
        return true;
    }

    // ── Normal drag path ──

    m_dragging.store(true);

    // Modifier key snapshot (Win32 nFlags lacks MK_ALT)
    bool altHeld   = (::GetKeyState(VK_MENU) & 0x8000) != 0;
    bool ctrlHeld  = (::GetKeyState(VK_CONTROL) & 0x8000) != 0;
    bool shiftHeld = (::GetKeyState(VK_SHIFT) & 0x8000) != 0;

    // ── Save and configure drag settings ──
    int  prevScaleMode = m_conduit->m_drag_settings.m_scale_mode;
    bool prevSnapping  = m_conduit->m_drag_settings.m_bSnappingEnabled;
    bool prevRelocate  = m_conduit->m_drag_settings.m_bRelocateGumball;

    // Shift + scale handle → uniform scale (m_scale_mode: 0=independent,
    // 1=xy, 2=yz, 3=zx, 4=xyz — per CRhinoGumballDragSettings docs)
    bool isScaleMode = (pickedMode >= gb_mode_scalex && pickedMode <= gb_mode_scalezx);
    if (isScaleMode && shiftHeld)
        m_conduit->m_drag_settings.m_scale_mode = 4;

    // Snappy/smooth dragging
    m_conduit->m_drag_settings.m_bSnappingEnabled = m_snappyDragging.load();

    // Ctrl = relocate gumball (matches Rhino's native behavior).
    // The SDK's CRhinoGumballDragger also calls CheckShiftAndControlKeys()
    // during the drag loop, so Ctrl pressed mid-drag works too.
    if (ctrlHeld)
        m_conduit->m_drag_settings.m_bRelocateGumball = true;

    // ── Run the drag via CRhinoGumballDragger ──
    ON_Xform totalXform = ON_Xform::IdentityTransformation;
    bool dragApplied = false;

    {
        CRhinoGumballDragger dragger(*m_conduit);
        CRhinoGet::result rc = dragger.DragGumball();

        if (rc == CRhinoGet::point || rc == CRhinoGet::nothing)
        {
            totalXform = m_conduit->TotalTransform();
            if (IsTranslationLikeMode(pickedMode))
                ScaleTranslationComponents(totalXform, m_dragStrength.load());
            dragApplied = true;
        }
    }

    // Check if relocate happened (Ctrl at start OR pressed during drag)
    bool wasRelocated = m_conduit->m_drag_settings.m_bRelocateGumball;

    // Restore original drag settings
    m_conduit->m_drag_settings.m_scale_mode       = prevScaleMode;
    m_conduit->m_drag_settings.m_bSnappingEnabled  = prevSnapping;
    m_conduit->m_drag_settings.m_bRelocateGumball  = prevRelocate;

    // Detect extrude handle modes (the separate extrude dot handles)
    bool isExtrudeMode = (pickedMode == gb_mode_extrudex
                          || pickedMode == gb_mode_extrudey
                          || pickedMode == gb_mode_extrudez);

    // ════════════════════════════════════════════════════════════════
    // Post-drag: apply result based on mode
    // ════════════════════════════════════════════════════════════════

    bool copyMade = false;

    if (wasRelocated && dragApplied)
    {
        // ── Relocate: reposition gumball without moving objects ──
        m_conduit->RelocateBaseGumball(m_conduit->Gumball().m_frame);
        RhinoApp().Print(L"[AIGumball] Gumball relocated (Ctrl+drag)\n");
    }
    else if (dragApplied && totalXform.IsValid() && !totalXform.IsIdentity())
    {
        CRhinoDoc* pDoc = GetDocument();
        if (pDoc)
        {
            // Capture sub-object selections BEFORE transform
            struct ObjSubSelection {
                ON_UUID uuid;
                ON_SimpleArray<ON_COMPONENT_INDEX> subIndices;
            };
            std::vector<ObjSubSelection> subSelections;

            for (const auto& uuid : m_selectedIds)
            {
                const CRhinoObject* pObj = pDoc->LookupObject(uuid);
                if (!pObj) continue;

                ObjSubSelection sel;
                sel.uuid = uuid;
                pObj->GetSelectedSubObjects(sel.subIndices);
                subSelections.push_back(std::move(sel));
            }

            // ── Alt = Copy ──
            if (altHeld)
            {
                std::vector<ON_UUID> newIds;
                for (const auto& uuid : m_selectedIds)
                {
                    const CRhinoObject* pObj = pDoc->LookupObject(uuid);
                    if (!pObj) continue;

                    const CRhinoObject* pNewObj = pDoc->TransformObject(
                        pObj, totalXform,
                        true,   // bAddNewObjectToDoc
                        false,  // bDeleteOriginal — keep original!
                        true    // bAddTransformHistory
                    );
                    if (pNewObj)
                        newIds.push_back(pNewObj->Attributes().m_uuid);
                }

                copyMade = !newIds.empty();

                for (const auto& uuid : m_selectedIds)
                {
                    const CRhinoObject* pObj = pDoc->LookupObject(uuid);
                    if (pObj) const_cast<CRhinoObject*>(pObj)->Select(false);
                }
                for (const auto& newId : newIds)
                {
                    const CRhinoObject* pObj = pDoc->LookupObject(newId);
                    if (pObj) const_cast<CRhinoObject*>(pObj)->Select(true);
                }

                m_selectedIds.clear();
                m_selectedIds.insert(m_selectedIds.end(),
                                     newIds.begin(), newIds.end());
                RhinoApp().Print(L"[AIGumball] Alt-copy: %d copies created\n",
                    static_cast<int>(newIds.size()));
            }
            // ── Extrude handle → extrude sub-object faces ──
            else if (isExtrudeMode)
            {
                ON_3dVector direction(totalXform[0][3],
                                     totalXform[1][3],
                                     totalXform[2][3]);

                if (direction.Length() > ON_ZERO_TOLERANCE)
                {
                    // Per-object fallback: if extrude fails for an object,
                    // apply transform to that object instead (matches numeric path).
                    for (const auto& uuid : m_selectedIds)
                    {
                        const CRhinoObject* pObj = pDoc->LookupObject(uuid);
                        if (!pObj) continue;

                        if (!ApplyExtrudeFaces(pDoc, pObj, direction))
                        {
                            if (!ApplySubObjectTransform(pDoc, pObj, totalXform))
                                pDoc->TransformObject(pObj, totalXform,
                                                      true, true, true);
                        }
                    }
                }
            }
            // ── Normal transform ──
            else
            {
                for (const auto& uuid : m_selectedIds)
                {
                    const CRhinoObject* pObj = pDoc->LookupObject(uuid);
                    if (!pObj) continue;

                    if (!ApplySubObjectTransform(pDoc, pObj, totalXform))
                        pDoc->TransformObject(pObj, totalXform, true, true, true);
                }
            }

            // Re-select objects and restore sub-object selections.
            if (!altHeld)
            {
                for (const auto& sel : subSelections)
                {
                    const CRhinoObject* pObj = pDoc->LookupObject(sel.uuid);
                    if (!pObj) continue;

                    if (sel.subIndices.Count() > 0)
                    {
                        for (int i = 0; i < sel.subIndices.Count(); i++)
                            pObj->SelectSubObject(sel.subIndices[i], true, true);
                    }
                    else
                    {
                        const_cast<CRhinoObject*>(pObj)->Select(true);
                    }
                }
            }
        }
    }

    // Record drag history (only for completed drags, not cancellations)
    if (dragApplied)
    {
        RecordDrag(totalXform, dragStart);

        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_dragHistory.empty())
        {
            m_dragHistory.back().isCopy = copyMade;
            m_dragHistory.back().isRelocate = wasRelocated;
        }
    }

    if (dragApplied && m_autoReset.load())
    {
        m_cumulativeTransform = ON_Xform::IdentityTransformation;

        std::lock_guard<std::mutex> lock(m_mutex);
        m_cumulativeXfArray = XformToArray(ON_Xform::IdentityTransformation);
    }

    m_dragging.store(false);
    m_inDragger = false;

    // Rebuild gumball (skip for relocate — already repositioned)
    if (!wasRelocated || !dragApplied)
        UpdateGumballFromSelection();

    return true;
}

// ════════════════════════════════════════════════════════════════════
// Drag History Recording
// ════════════════════════════════════════════════════════════════════

void CGumballManager::RecordDrag(const ON_Xform& totalXform,
                                  std::chrono::steady_clock::time_point dragStart)
{
    auto elapsed = std::chrono::steady_clock::now() - dragStart;
    double durationMs = std::chrono::duration<double, std::milli>(elapsed).count();

    m_cumulativeTransform = m_cumulativeTransform * totalXform;

    // Read handle mode from conduit pick result (26 possible modes)
    std::string mode = "unknown";
    if (m_conduit)
    {
        GUMBALL_MODE gm = m_conduit->m_pick_result.m_gumball_mode;
        switch (gm)
        {
        case gb_mode_translatex:    mode = "x_translate"; break;
        case gb_mode_translatey:    mode = "y_translate"; break;
        case gb_mode_translatez:    mode = "z_translate"; break;
        case gb_mode_translatexy:   mode = "xy_translate"; break;
        case gb_mode_translateyz:   mode = "yz_translate"; break;
        case gb_mode_translatezx:   mode = "zx_translate"; break;
        case gb_mode_translatefree: mode = "free_translate"; break;
        case gb_mode_rotatex:       mode = "x_rotate"; break;
        case gb_mode_rotatey:       mode = "y_rotate"; break;
        case gb_mode_rotatez:       mode = "z_rotate"; break;
        case gb_mode_scalex:        mode = "x_scale"; break;
        case gb_mode_scaley:        mode = "y_scale"; break;
        case gb_mode_scalez:        mode = "z_scale"; break;
        case gb_mode_scalexy:       mode = "xy_scale"; break;
        case gb_mode_scaleyz:       mode = "yz_scale"; break;
        case gb_mode_scalezx:       mode = "zx_scale"; break;
        case gb_mode_extrudex:      mode = "x_extrude"; break;
        case gb_mode_extrudey:      mode = "y_extrude"; break;
        case gb_mode_extrudez:      mode = "z_extrude"; break;
        case gb_mode_cutx:          mode = "x_cut"; break;
        case gb_mode_cuty:          mode = "y_cut"; break;
        case gb_mode_cutz:          mode = "z_cut"; break;
        case gb_mode_menu:          mode = "menu"; break;
        default:                    mode = "unknown"; break;
        }
    }

    std::lock_guard<std::mutex> lock(m_mutex);
    m_dragCount++;
    m_lastMode = mode;
    m_cumulativeXfArray = XformToArray(m_cumulativeTransform);

    GumballDragRecord rec;
    rec.dragIndex = m_dragCount;
    rec.handleMode = mode;
    rec.deltaTransform = XformToArray(totalXform);
    rec.cumulativeTransform = m_cumulativeXfArray;
    rec.timestamp = NowIso8601();
    rec.dragDurationMs = durationMs;
    m_dragHistory.push_back(std::move(rec));
}

// ════════════════════════════════════════════════════════════════════
// Gumball Display
// ════════════════════════════════════════════════════════════════════

void CGumballManager::UpdateGumballFromSelection()
{
    CRhinoDoc* pDoc = GetDocument();
    if (!pDoc) return;

    m_selectedIds.clear();

    // Get currently selected objects
    CRhinoObjectIterator it(*pDoc,
        CRhinoObjectIterator::normal_or_locked_objects,
        CRhinoObjectIterator::active_objects);
    for (const CRhinoObject* pObj = it.First(); pObj; pObj = it.Next())
    {
        // bCheckSubObjects=true: returns 3 when sub-objects (faces, edges)
        // are selected even if the whole object isn't. Without this, the
        // gumball disappears on sub-object selection.
        if (pObj->IsSelected(true))
            m_selectedIds.push_back(pObj->Attributes().m_uuid);
    }

    RhinoApp().Print(L"[AIGumball] UpdateGumballFromSelection: %d objects selected\n",
        static_cast<int>(m_selectedIds.size()));

    if (!m_selectedIds.empty())
        ShowGumball();
    else
        HideGumball();
}

void CGumballManager::ShowGumball()
{
    CRhinoDoc* pDoc = GetDocument();
    if (!pDoc) return;

    // Compute bounding box. If sub-objects are selected, use their bbox
    // so the gumball centers on the selected face/edge/vertex.
    ON_BoundingBox bbox;
    bool hasSubObjects = false;

    for (const auto& uuid : m_selectedIds)
    {
        const CRhinoObject* pObj = pDoc->LookupObject(uuid);
        if (!pObj || !pObj->Geometry()) continue;

        ON_SimpleArray<ON_COMPONENT_INDEX> subIndices;
        int subCount = pObj->GetSelectedSubObjects(subIndices);
        if (subCount > 0)
        {
            hasSubObjects = true;
            const ON_Brep* pBrep = ON_Brep::Cast(pObj->Geometry());
            for (int i = 0; i < subIndices.Count(); i++)
            {
                ON_COMPONENT_INDEX ci = subIndices[i];
                if (pBrep)
                {
                    if (ci.m_type == ON_COMPONENT_INDEX::brep_face
                        && ci.m_index >= 0 && ci.m_index < pBrep->m_F.Count())
                    {
                        ON_BoundingBox faceBbox = pBrep->m_F[ci.m_index].BoundingBox();
                        if (faceBbox.IsValid()) bbox.Union(faceBbox);
                    }
                    else if (ci.m_type == ON_COMPONENT_INDEX::brep_edge
                        && ci.m_index >= 0 && ci.m_index < pBrep->m_E.Count())
                    {
                        ON_BoundingBox edgeBbox = pBrep->m_E[ci.m_index].BoundingBox();
                        if (edgeBbox.IsValid()) bbox.Union(edgeBbox);
                    }
                    else if (ci.m_type == ON_COMPONENT_INDEX::brep_vertex
                        && ci.m_index >= 0 && ci.m_index < pBrep->m_V.Count())
                    {
                        ON_3dPoint pt = pBrep->m_V[ci.m_index].point;
                        bbox.Union(ON_BoundingBox(pt, pt));
                    }
                }
            }
        }
    }

    // Inflate degenerate sub-object bboxes (edge lines, vertex points)
    if (hasSubObjects && bbox.IsValid())
    {
        ON_3dVector diag = bbox.Diagonal();
        if (diag.Length() < pDoc->AbsoluteTolerance() * 10)
        {
            double pad = (std::max)(diag.Length() * 0.15,
                                    pDoc->AbsoluteTolerance() * 100);
            bbox.m_min -= ON_3dVector(pad, pad, pad);
            bbox.m_max += ON_3dVector(pad, pad, pad);
        }
    }

    // Fallback: whole-object bbox when no sub-objects or sub-object bbox failed
    if (!bbox.IsValid())
    {
        for (const auto& uuid : m_selectedIds)
        {
            const CRhinoObject* pObj = pDoc->LookupObject(uuid);
            if (pObj && pObj->Geometry())
            {
                ON_BoundingBox objBbox = pObj->Geometry()->BoundingBox();
                if (objBbox.IsValid())
                    bbox.Union(objBbox);
            }
        }
    }

    if (!bbox.IsValid())
    {
        RhinoApp().Print(L"[AIGumball] ShowGumball: bbox invalid, aborting\n");
        return;
    }

    CRhinoGumball gumball(ON::model_space);
    bool frameSet = false;

    // v2: Geometry-aware alignment for single-object selections.
    if (m_alignmentMode == AlignmentMode::Object && m_selectedIds.size() == 1)
    {
        const CRhinoObject* pObj = pDoc->LookupObject(m_selectedIds[0]);
        if (pObj)
        {
            switch (pObj->ObjectType())
            {
            case ON::brep_object:
            {
                const CRhinoBrepObject* pBrepObj = CRhinoBrepObject::Cast(pObj);
                if (pBrepObj)
                    frameSet = gumball.SetFromBrepObject(*pBrepObj);
                break;
            }
            case ON::extrusion_object:
                break;
            case ON::curve_object:
            {
                const ON_Curve* pCurve = ON_Curve::Cast(pObj->Geometry());
                if (pCurve)
                    frameSet = gumball.SetFromCurve(*pCurve);
                break;
            }
            case ON::mesh_object:
            {
                const CRhinoMeshObject* pMeshObj = CRhinoMeshObject::Cast(pObj);
                if (pMeshObj)
                    frameSet = gumball.SetFromMeshObject(*pMeshObj);
                break;
            }
            case ON::subd_object:
            {
                const CRhinoSubDObject* pSubDObj = CRhinoSubDObject::Cast(pObj);
                if (pSubDObj)
                    frameSet = gumball.SetFromSubDObject(*pSubDObj);
                break;
            }
            default:
                break;
            }
        }
    }
    else if (m_alignmentMode == AlignmentMode::CPlane)
    {
        CRhinoView* pView = RhinoApp().ActiveView();
        if (pView)
        {
            ON_Plane cplane = pView->ActiveViewport().ConstructionPlane().m_plane;
            cplane.SetOrigin(bbox.Center());
            gumball.SetFromBoundingBox(bbox);
            gumball.m_frame.m_plane = cplane;
            frameSet = true;
        }
    }

    // Fallback: world-aligned bounding box.
    // SetFromBoundingBox(plane, bbox) internally computes the center from
    // the bbox and offsets through the plane. If we pre-set the plane
    // origin to bbox.Center(), the offset doubles. Use world origin plane.
    if (!frameSet)
        gumball.SetFromBoundingBox(ON_Plane::World_xy, bbox);

    // When sub-objects are selected, re-center the gumball to the
    // sub-object bbox center. SetFrom*Object aligns axes to the whole
    // object — we keep those axes but move the origin to the sub-selection.
    // SetCenter() preserves axis directions. Scale grips also need
    // updating via SetScaleFromBoundingBox so they fit the sub-object.
    if (hasSubObjects && bbox.IsValid())
    {
        gumball.SetCenter(bbox.Center());
        gumball.m_frame.SetScaleFromBoundingBox(gumball.m_frame.m_plane, bbox);
    }

    // Enable extrude dot handles for Brep and Extrusion selections.
    // CRhinoGumballAppearance defaults m_bEnableX/Y/ZExtrude to false.
    // Rhino's native gumball shows extrude dots when the selection can be
    // extruded — that means Breps (solids/surfaces) and extrusions.
    {
        bool enableExtrude = false;
        for (const auto& uuid : m_selectedIds)
        {
            const CRhinoObject* pObj = pDoc->LookupObject(uuid);
            if (!pObj) continue;
            ON::object_type ot = pObj->ObjectType();
            if (ot == ON::brep_object || ot == ON::extrusion_object
                || ot == ON::subd_object)
            {
                enableExtrude = true;
                break;
            }
        }
        if (enableExtrude)
        {
            gumball.m_appearance.m_bEnableXExtrude = true;
            gumball.m_appearance.m_bEnableYExtrude = true;
            gumball.m_appearance.m_bEnableZExtrude = true;
        }
    }

    // Validate gumball frame before giving it to the conduit
    const ON_3dPoint& center = gumball.m_frame.Center();
    const ON_3dVector& xAxis = gumball.m_frame.Axis(0);
    bool planeValid = gumball.m_frame.m_plane.IsValid();
    RhinoApp().Print(L"[AIGumball] ShowGumball: center=(%.2f,%.2f,%.2f) "
        L"xAxis=(%.4f,%.4f,%.4f) planeValid=%d frameSet=%d\n",
        center.x, center.y, center.z,
        xAxis.x, xAxis.y, xAxis.z,
        planeValid ? 1 : 0, frameSet ? 1 : 0);

    // Create conduit if needed. Reuse the existing one when possible
    // to avoid unnecessary heap churn. Only recreate if the conduit
    // doesn't exist (first call or after Deactivate).
    if (!m_conduit)
        m_conduit = new CRhinoGumballDisplayConduit(ON::model_space);

    bool setOk = m_conduit->SetBaseGumball(gumball);
    RhinoApp().Print(L"[AIGumball] SetBaseGumball returned %d\n", setOk ? 1 : 0);

    if (!setOk)
    {
        // Gumball data is invalid — the conduit will not draw.
        RhinoApp().Print(L"[AIGumball] ERROR: SetBaseGumball rejected the gumball!\n");
        return;
    }

    m_conduit->EnableGumballDraw(true);
    m_conduit->Enable(pDoc->RuntimeSerialNumber());

    // Verify state immediately after enabling
    bool isEn = m_conduit->IsEnabled();
    bool isDraw = m_conduit->GumballDrawIsEnabled();
    RhinoApp().Print(L"[AIGumball] After Enable: IsEnabled=%d GumballDrawIsEnabled=%d "
        L"docSn=%u\n", isEn ? 1 : 0, isDraw ? 1 : 0,
        pDoc->RuntimeSerialNumber());

    pDoc->Redraw();
}

void CGumballManager::HideGumball()
{
    if (m_conduit)
    {
        m_conduit->EnableGumballDraw(false);
        RhinoApp().Print(L"[AIGumball] HideGumball: draw disabled, conduit still enabled=%d\n",
            m_conduit->IsEnabled() ? 1 : 0);
    }

    CRhinoDoc* pDoc = GetDocument();
    if (pDoc) pDoc->Redraw();
}

// ════════════════════════════════════════════════════════════════════
// Selection Watcher
// ════════════════════════════════════════════════════════════════════

CGumballManager::CSelectionWatcher::CSelectionWatcher(CGumballManager& owner)
    : m_owner(owner)
{
}

void CGumballManager::CSelectionWatcher::OnSelectObject(CRhinoDoc& /*doc*/, const CRhinoObject& /*object*/)
{
    if (!m_owner.m_enabled.load() || m_owner.m_dragging.load()) return;
    m_owner.UpdateGumballFromSelection();
}

void CGumballManager::CSelectionWatcher::OnSelectObjects(CRhinoDoc& /*doc*/, const ON_SimpleArray<const CRhinoObject*>& /*objects*/)
{
    if (!m_owner.m_enabled.load() || m_owner.m_dragging.load()) return;
    m_owner.UpdateGumballFromSelection();
}

void CGumballManager::CSelectionWatcher::OnDeselectObject(CRhinoDoc& /*doc*/, const CRhinoObject& /*object*/)
{
    if (!m_owner.m_enabled.load() || m_owner.m_dragging.load()) return;
    m_owner.UpdateGumballFromSelection();
}

void CGumballManager::CSelectionWatcher::OnDeselectObjects(CRhinoDoc& /*doc*/, const ON_SimpleArray<const CRhinoObject*>& /*objects*/)
{
    if (!m_owner.m_enabled.load() || m_owner.m_dragging.load()) return;
    m_owner.UpdateGumballFromSelection();
}

void CGumballManager::CSelectionWatcher::OnDeselectAllObjects(CRhinoDoc& /*doc*/, int /*count*/)
{
    if (!m_owner.m_enabled.load() || m_owner.m_dragging.load()) return;
    m_owner.UpdateGumballFromSelection();
}

void CGumballManager::CSelectionWatcher::OnEndCommand(
    const CRhinoCommand& /*command*/,
    const CRhinoCommandContext& /*context*/,
    CRhinoCommand::result /*rc*/)
{
    // After any command ends, update gumball to reflect selection changes
    if (!m_owner.m_enabled.load() || m_owner.m_dragging.load()) return;
    m_owner.UpdateGumballFromSelection();
}

// ════════════════════════════════════════════════════════════════════
// Snappy/Smooth & Alignment Cycling
// ════════════════════════════════════════════════════════════════════

void CGumballManager::SetSnappy(bool enabled)
{
    m_snappyDragging.store(enabled);
    RhinoApp().Print(L"[AIGumball] Snappy dragging: %s\n",
        enabled ? L"ON" : L"OFF");
}

AlignmentMode CGumballManager::CycleAlignment()
{
    AlignmentMode current = m_alignmentMode.load();
    AlignmentMode next;
    switch (current)
    {
    case AlignmentMode::World:  next = AlignmentMode::Object; break;
    case AlignmentMode::Object: next = AlignmentMode::CPlane; break;
    case AlignmentMode::CPlane: next = AlignmentMode::World;  break;
    default:                    next = AlignmentMode::World;  break;
    }
    m_alignmentMode.store(next);

    // Update the gumball to reflect the new alignment
    if (m_enabled.load() && !m_selectedIds.empty())
        ShowGumball();

    const wchar_t* name = L"World";
    if (next == AlignmentMode::Object) name = L"Object";
    else if (next == AlignmentMode::CPlane) name = L"CPlane";
    RhinoApp().Print(L"[AIGumball] Alignment: %s\n", name);

    return next;
}

// ════════════════════════════════════════════════════════════════════
// Thread-Safe Queries (for HTTP handlers)
// ════════════════════════════════════════════════════════════════════

int CGumballManager::GetDragCount() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_dragCount;
}

std::string CGumballManager::GetLastMode() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_lastMode;
}

std::array<double, 16> CGumballManager::GetCumulativeTransform() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_cumulativeXfArray;
}

std::vector<GumballDragRecord> CGumballManager::GetHistory(int limit) const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    std::vector<GumballDragRecord> result;
    int start = (std::max)(0, static_cast<int>(m_dragHistory.size()) - limit);
    for (int i = start; i < static_cast<int>(m_dragHistory.size()); i++)
        result.push_back(m_dragHistory[i]);
    return result;
}

} // namespace Rook
