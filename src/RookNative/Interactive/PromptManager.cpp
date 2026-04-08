// PromptManager.cpp
//
// Heap-allocated shared state pattern for each prompt type.
// Main thread runs GetPoint/GetObject in a modal loop; HTTP thread waits on cv.
//
// THREAD SAFETY: Shared state (result, mutex, cv, done flag) lives in a
// shared_ptr on the heap. Both the HTTP thread and the main-thread lambda
// hold a shared_ptr copy. This prevents use-after-free if the HTTP thread
// times out and returns before the lambda finishes — the lambda writes to
// heap memory that stays alive until its shared_ptr is released.
//
// cv.notify_one() is always called INSIDE the lock to prevent notification
// on a destroyed condition_variable.

#include "stdafx.h"
#include "Interactive/PromptManager.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"

#include <mutex>
#include <condition_variable>
#include <chrono>
#include <memory>

namespace Rook {

// ════════════════════════════════════════════════════════════════════
// C8 fix: Prompt busy guard — prevents concurrent modal prompts
// ════════════════════════════════════════════════════════════════════

static std::atomic<bool> s_promptActive{false};

bool IsPromptActive()
{
    return s_promptActive.load(std::memory_order_acquire);
}

// ════════════════════════════════════════════════════════════════════
// Shared state template — heap-allocated, shared between threads
// ════════════════════════════════════════════════════════════════════

namespace {

// C8 fix: RAII guard that acquires the prompt-active flag via CAS.
// If another prompt is already active, `acquired` will be false.
// The destructor releases the flag only if this guard acquired it.
struct PromptGuard
{
    bool acquired;
    PromptGuard() : acquired(false)
    {
        bool expected = false;
        acquired = s_promptActive.compare_exchange_strong(
            expected, true, std::memory_order_acq_rel);
    }
    ~PromptGuard()
    {
        if (acquired)
            s_promptActive.store(false, std::memory_order_release);
    }
    PromptGuard(const PromptGuard&) = delete;
    PromptGuard& operator=(const PromptGuard&) = delete;
};

template<typename ResultT>
struct PromptState
{
    ResultT result;
    std::mutex mtx;
    std::condition_variable cv;
    bool done = false;
};

// ════════════════════════════════════════════════════════════════════
// Geometry filter mapping (string -> ON::object_type bitmask)
// ════════════════════════════════════════════════════════════════════

unsigned int ParseGeometryFilter(const std::string& filter)
{
    if (filter == "point")     return ON::point_object;
    if (filter == "curve")     return ON::curve_object;
    if (filter == "surface")   return ON::surface_object;
    if (filter == "brep")      return ON::brep_object;
    if (filter == "mesh")      return ON::mesh_object;
    if (filter == "subd")      return ON::subd_object;
    if (filter == "extrusion") return ON::extrusion_object;
    if (filter == "annotation")return ON::annotation_object;
    if (filter == "block")     return ON::instance_reference;
    return 0xFFFFFFFF; // any
}

// ON_COMPONENT_INDEX type -> string
std::string ComponentTypeToString(ON_COMPONENT_INDEX::TYPE type)
{
    switch (type)
    {
    case ON_COMPONENT_INDEX::brep_face:   return "brep_face";
    case ON_COMPONENT_INDEX::brep_edge:   return "brep_edge";
    case ON_COMPONENT_INDEX::brep_vertex: return "brep_vertex";
    default:                              return "unknown";
    }
}

// Fire-and-forget Escape dispatch — used by all prompt timeout paths.
// Captures nothing — no risk of dangling references.
void PostEscapeToRhino()
{
    CMainThreadDispatcher::Instance().Dispatch([]() {
        HWND hWnd = RhinoApp().MainWnd();
        if (hWnd)
            ::PostMessage(hWnd, WM_KEYDOWN, VK_ESCAPE, 0);
    });
}

} // anonymous namespace

// ════════════════════════════════════════════════════════════════════
// PromptForPoint
// ════════════════════════════════════════════════════════════════════

PointResult PromptForPoint(const std::string& message,
                           const double* basePoint,
                           const std::string& constrainToObjectId,
                           int timeoutSeconds)
{
    // C8 fix: Only one prompt at a time
    PromptGuard guard;
    if (!guard.acquired)
    {
        PointResult r;
        r.error = "Another prompt is already active";
        return r;
    }

    auto state = std::make_shared<PromptState<PointResult>>();

    ON_wString wMessage = Utf8ToWide(message);

    // Capture constraint params by value for the lambda
    bool hasBase = (basePoint != nullptr);
    ON_3dPoint basePt;
    if (hasBase) basePt.Set(basePoint[0], basePoint[1], basePoint[2]);

    std::string constrainId = constrainToObjectId;

    CMainThreadDispatcher::Instance().Dispatch(
        [state, wMessage, hasBase, basePt, constrainId]()
    {
        CRhinoGetPoint gp;
        gp.SetCommandPrompt(static_cast<const wchar_t*>(wMessage));

        if (hasBase)
            gp.SetBasePoint(basePt, TRUE);

        // Constrain to object surface if specified
        if (!constrainId.empty())
        {
            CRhinoDoc* pDoc = GetDocument();
            if (pDoc)
            {
                ON_UUID uuid = ON_UuidFromString(constrainId.c_str());
                if (ON_UuidCompare(uuid, ON_nil_uuid) != 0)
                {
                    const CRhinoObject* pObj = pDoc->LookupObject(uuid);
                    if (pObj && pObj->Geometry())
                    {
                        const ON_Geometry* geom = pObj->Geometry();
                        if (const ON_Brep* pBrep = ON_Brep::Cast(geom))
                            gp.Constrain(*pBrep);
                        else if (const ON_Mesh* pMesh = ON_Mesh::Cast(geom))
                            gp.Constrain(*pMesh);
                        else if (const ON_Surface* pSrf = ON_Surface::Cast(geom))
                            gp.Constrain(*pSrf);
                    }
                }
            }
        }

        auto rc = gp.GetPoint();

        {
            std::lock_guard<std::mutex> lock(state->mtx);
            if (rc == CRhinoGet::point)
            {
                ON_3dPoint pt = gp.Point();
                state->result.success = true;
                state->result.point = { pt.x, pt.y, pt.z };
            }
            else
            {
                state->result.cancelled = true;
            }
            state->done = true;
            state->cv.notify_one();
        }
    });

    // Wait on condition_variable with timeout.
    // All writes to state->result must happen under state->mtx to avoid
    // a data race with the main-thread lambda (which also writes under lock).
    std::unique_lock<std::mutex> lock(state->mtx);
    bool completed = state->cv.wait_for(lock,
        std::chrono::seconds(timeoutSeconds), [&] { return state->done; });

    if (!completed)
        state->result.error = "Timeout waiting for user input";

    // Copy result while holding the lock — the main-thread lambda may still
    // be running and could write to state->result after we release.
    auto resultCopy = state->result;
    lock.unlock();

    if (!completed)
        PostEscapeToRhino();

    return resultCopy;
}

// ════════════════════════════════════════════════════════════════════
// PromptForObject
// ════════════════════════════════════════════════════════════════════

ObjectResult PromptForObject(const std::string& message,
                             const std::string& filter,
                             int timeoutSeconds)
{
    // C8 fix: Only one prompt at a time
    PromptGuard guard;
    if (!guard.acquired)
    {
        ObjectResult r;
        r.error = "Another prompt is already active";
        return r;
    }

    auto state = std::make_shared<PromptState<ObjectResult>>();

    ON_wString wMessage = Utf8ToWide(message);
    unsigned int geoFilter = ParseGeometryFilter(filter);

    CMainThreadDispatcher::Instance().Dispatch(
        [state, wMessage, geoFilter]()
    {
        CRhinoGetObject go;
        go.SetCommandPrompt(static_cast<const wchar_t*>(wMessage));
        go.SetGeometryFilter(geoFilter);

        auto rc = go.GetObjects(1, 1);

        {
            std::lock_guard<std::mutex> lock(state->mtx);
            if (rc == CRhinoGet::object && go.ObjectCount() > 0)
            {
                const CRhinoObjRef& objRef = go.Object(0);
                const CRhinoObject* pObj = objRef.Object();
                if (pObj)
                {
                    state->result.success = true;
                    state->result.id = UuidToString(pObj->Attributes().m_uuid);
                    state->result.type = ObjectTypeToString(pObj->ObjectType());

                    ON_wString wName = pObj->Attributes().m_name;
                    if (!wName.IsEmpty())
                        state->result.name = WideToUtf8(wName);

                    // C22 fix: Populate the layer field from the object's layer index.
                    CRhinoDoc* pDoc = GetDocument();
                    if (pDoc)
                    {
                        int layerIdx = pObj->Attributes().m_layer_index;
                        if (layerIdx >= 0 && layerIdx < pDoc->m_layer_table.LayerCount())
                        {
                            const CRhinoLayer& layer = pDoc->m_layer_table[layerIdx];
                            state->result.layer = WideToUtf8(layer.Name());
                        }
                    }

                    ON_3dPoint selPt;
                    if (objRef.SelectionPoint(selPt))
                    {
                        state->result.pickPoint = { selPt.x, selPt.y, selPt.z };
                        state->result.hasPickPoint = true;
                    }
                }
                else
                {
                    state->result.cancelled = true;
                }
            }
            else
            {
                state->result.cancelled = true;
            }
            state->done = true;
            state->cv.notify_one();
        }
    });

    std::unique_lock<std::mutex> lock(state->mtx);
    bool completed = state->cv.wait_for(lock,
        std::chrono::seconds(timeoutSeconds), [&] { return state->done; });

    if (!completed)
        state->result.error = "Timeout waiting for user input";

    auto resultCopy = state->result;
    lock.unlock();

    if (!completed)
        PostEscapeToRhino();

    return resultCopy;
}

// ════════════════════════════════════════════════════════════════════
// PromptForObjects
// ════════════════════════════════════════════════════════════════════

MultiObjectResult PromptForObjects(const std::string& message,
                                    const std::string& filter,
                                    int minCount,
                                    int timeoutSeconds)
{
    // C8 fix: Only one prompt at a time
    PromptGuard guard;
    if (!guard.acquired)
    {
        MultiObjectResult r;
        r.error = "Another prompt is already active";
        return r;
    }

    auto state = std::make_shared<PromptState<MultiObjectResult>>();

    ON_wString wMessage = Utf8ToWide(message);
    unsigned int geoFilter = ParseGeometryFilter(filter);

    CMainThreadDispatcher::Instance().Dispatch(
        [state, wMessage, geoFilter, minCount]()
    {
        CRhinoGetObject go;
        go.SetCommandPrompt(static_cast<const wchar_t*>(wMessage));
        go.SetGeometryFilter(geoFilter);

        auto rc = go.GetObjects(minCount, 0);  // 0 = no max

        {
            std::lock_guard<std::mutex> lock(state->mtx);
            if (rc == CRhinoGet::object && go.ObjectCount() > 0)
            {
                state->result.success = true;
                for (int i = 0; i < go.ObjectCount(); i++)
                {
                    const CRhinoObjRef& objRef = go.Object(i);
                    const CRhinoObject* pObj = objRef.Object();
                    if (!pObj) continue;

                    ObjectResult obj;
                    obj.success = true;
                    obj.id = UuidToString(pObj->Attributes().m_uuid);
                    obj.type = ObjectTypeToString(pObj->ObjectType());

                    ON_wString wName = pObj->Attributes().m_name;
                    if (!wName.IsEmpty())
                        obj.name = WideToUtf8(wName);

                    // C22 fix: Populate layer field for multi-select too.
                    CRhinoDoc* pDoc = GetDocument();
                    if (pDoc)
                    {
                        int layerIdx = pObj->Attributes().m_layer_index;
                        if (layerIdx >= 0 && layerIdx < pDoc->m_layer_table.LayerCount())
                        {
                            const CRhinoLayer& layer = pDoc->m_layer_table[layerIdx];
                            obj.layer = WideToUtf8(layer.Name());
                        }
                    }

                    state->result.objects.push_back(std::move(obj));
                }
            }
            else
            {
                state->result.cancelled = true;
            }
            state->done = true;
            state->cv.notify_one();
        }
    });

    std::unique_lock<std::mutex> lock(state->mtx);
    bool completed = state->cv.wait_for(lock,
        std::chrono::seconds(timeoutSeconds), [&] { return state->done; });

    if (!completed)
        state->result.error = "Timeout waiting for user input";

    auto resultCopy = state->result;
    lock.unlock();

    if (!completed)
        PostEscapeToRhino();

    return resultCopy;
}

// ════════════════════════════════════════════════════════════════════
// PromptForSubObject
// ════════════════════════════════════════════════════════════════════

SubObjectResult PromptForSubObject(const std::string& message,
                                    const std::string& subFilter,
                                    int timeoutSeconds)
{
    // C8 fix: Only one prompt at a time
    PromptGuard guard;
    if (!guard.acquired)
    {
        SubObjectResult r;
        r.error = "Another prompt is already active";
        return r;
    }

    auto state = std::make_shared<PromptState<SubObjectResult>>();

    ON_wString wMessage = Utf8ToWide(message);

    CMainThreadDispatcher::Instance().Dispatch(
        [state, wMessage, subFilter]()
    {
        CRhinoGetObject go;
        go.SetCommandPrompt(static_cast<const wchar_t*>(wMessage));
        go.EnableSubObjectSelect(TRUE);

        // Set geometry filter based on subobject type
        if (subFilter == "face")
            go.SetGeometryFilter(ON::surface_object);
        else if (subFilter == "edge")
            go.SetGeometryFilter(ON::curve_object);
        else if (subFilter == "vertex")
            go.SetGeometryFilter(ON::point_object);
        else
            go.SetGeometryFilter(0xFFFFFFFF);

        auto rc = go.GetObjects(1, 1);

        {
            std::lock_guard<std::mutex> lock(state->mtx);
            if (rc == CRhinoGet::object && go.ObjectCount() > 0)
            {
                const CRhinoObjRef& objRef = go.Object(0);
                const CRhinoObject* pObj = objRef.Object();
                if (!pObj)
                {
                    state->result.cancelled = true;
                    state->done = true;
                    state->cv.notify_one();
                    return;
                }

                state->result.success = true;
                state->result.parentId = UuidToString(pObj->Attributes().m_uuid);
                state->result.parentType = ObjectTypeToString(pObj->ObjectType());

                ON_COMPONENT_INDEX ci = objRef.GeometryComponentIndex();
                state->result.componentType = ComponentTypeToString(ci.m_type);
                state->result.componentIndex = ci.m_index;

                // Extract geometry info from brep component
                const ON_Geometry* geom = pObj->Geometry();
                const ON_Brep* pBrep = geom ? ON_Brep::Cast(geom) : nullptr;

                // C3 fix: BrepForm() returns an owning pointer — wrap in unique_ptr
                // to prevent memory leaks when the object is an extrusion.
                std::unique_ptr<ON_Brep> brepOwner;
                if (!pBrep && geom)
                {
                    const ON_Extrusion* pExtr = ON_Extrusion::Cast(geom);
                    if (pExtr)
                    {
                        brepOwner.reset(pExtr->BrepForm());
                        pBrep = brepOwner.get();
                    }
                }

                if (pBrep)
                {
                    if (ci.m_type == ON_COMPONENT_INDEX::brep_face &&
                        ci.m_index >= 0 && ci.m_index < pBrep->m_F.Count())
                    {
                        const ON_BrepFace& face = pBrep->m_F[ci.m_index];
                        ON_MassProperties mp;
                        if (face.AreaMassProperties(mp, true, true, false, false))
                        {
                            state->result.area = mp.Area();
                            state->result.hasArea = true;
                            ON_3dPoint c = mp.Centroid();
                            state->result.centroid = { c.x, c.y, c.z };
                            state->result.hasCentroid = true;
                        }
                        // Normal at center
                        ON_Interval uDom = face.Domain(0);
                        ON_Interval vDom = face.Domain(1);
                        ON_3dPoint srfPt;
                        ON_3dVector srfNorm;
                        if (face.EvNormal(uDom.Mid(), vDom.Mid(), srfPt, srfNorm))
                        {
                            state->result.normal = { srfNorm.x, srfNorm.y, srfNorm.z };
                            state->result.hasNormal = true;
                        }
                    }
                    else if (ci.m_type == ON_COMPONENT_INDEX::brep_edge &&
                             ci.m_index >= 0 && ci.m_index < pBrep->m_E.Count())
                    {
                        const ON_BrepEdge& edge = pBrep->m_E[ci.m_index];
                        double edgeLen = 0.0;
                        if (edge.IsValid()) edge.GetLength(&edgeLen);
                        state->result.length = edgeLen;
                        state->result.hasLength = true;
                        ON_3dPoint s = edge.PointAtStart();
                        ON_3dPoint e = edge.PointAtEnd();
                        state->result.startPoint = { s.x, s.y, s.z };
                        state->result.endPoint = { e.x, e.y, e.z };
                        state->result.hasStartEnd = true;
                    }
                    else if (ci.m_type == ON_COMPONENT_INDEX::brep_vertex &&
                             ci.m_index >= 0 && ci.m_index < pBrep->m_V.Count())
                    {
                        const ON_BrepVertex& vert = pBrep->m_V[ci.m_index];
                        state->result.location = { vert.point.x, vert.point.y, vert.point.z };
                        state->result.hasLocation = true;
                    }
                }

                // Pick point
                ON_3dPoint selPt;
                if (objRef.SelectionPoint(selPt))
                {
                    state->result.pickPoint = { selPt.x, selPt.y, selPt.z };
                    state->result.hasPickPoint = true;
                }
            }
            else
            {
                state->result.cancelled = true;
            }
            state->done = true;
            state->cv.notify_one();
        }
    });

    std::unique_lock<std::mutex> lock(state->mtx);
    bool completed = state->cv.wait_for(lock,
        std::chrono::seconds(timeoutSeconds), [&] { return state->done; });

    if (!completed)
        state->result.error = "Timeout waiting for user input";

    auto resultCopy = state->result;
    lock.unlock();

    if (!completed)
        PostEscapeToRhino();

    return resultCopy;
}

// ════════════════════════════════════════════════════════════════════
// PromptForDistance
// ════════════════════════════════════════════════════════════════════

// C19 note: timeoutSeconds covers BOTH points combined. If the user takes
// 110 seconds on point 1, they get only 10 seconds for point 2 (with the
// default 120s timeout). This is acceptable because:
// 1. The shared_ptr heap state (C1 fix) prevents UAF on timeout.
// 2. Splitting into two dispatches would complicate cancellation semantics.
// 3. Clients can pass a larger timeout if they expect slow interaction.
DistanceResult PromptForDistance(const std::string& message1,
                                 const std::string& message2,
                                 int timeoutSeconds)
{
    // C8 fix: Only one prompt at a time
    PromptGuard guard;
    if (!guard.acquired)
    {
        DistanceResult r;
        r.error = "Another prompt is already active";
        return r;
    }

    auto state = std::make_shared<PromptState<DistanceResult>>();

    ON_wString wMsg1 = Utf8ToWide(message1);
    ON_wString wMsg2 = Utf8ToWide(message2);

    CMainThreadDispatcher::Instance().Dispatch(
        [state, wMsg1, wMsg2]()
    {
        // First point
        CRhinoGetPoint gp1;
        gp1.SetCommandPrompt(static_cast<const wchar_t*>(wMsg1));
        auto rc1 = gp1.GetPoint();

        if (rc1 != CRhinoGet::point)
        {
            std::lock_guard<std::mutex> lock(state->mtx);
            state->result.cancelled = true;
            state->done = true;
            state->cv.notify_one();
            return;
        }

        ON_3dPoint pt1 = gp1.Point();

        // Second point with visual feedback line
        CRhinoGetPoint gp2;
        gp2.SetCommandPrompt(static_cast<const wchar_t*>(wMsg2));
        gp2.SetBasePoint(pt1, TRUE);
        gp2.DrawLineFromPoint(pt1, TRUE);
        auto rc2 = gp2.GetPoint();

        {
            std::lock_guard<std::mutex> lock(state->mtx);
            if (rc2 == CRhinoGet::point)
            {
                ON_3dPoint pt2 = gp2.Point();
                state->result.success = true;
                state->result.point1 = { pt1.x, pt1.y, pt1.z };
                state->result.point2 = { pt2.x, pt2.y, pt2.z };
                state->result.distance = pt1.DistanceTo(pt2);
                ON_3dVector vec = pt2 - pt1;
                state->result.vector = { vec.x, vec.y, vec.z };
            }
            else
            {
                state->result.cancelled = true;
            }
            state->done = true;
            state->cv.notify_one();
        }
    });

    std::unique_lock<std::mutex> lock(state->mtx);
    bool completed = state->cv.wait_for(lock,
        std::chrono::seconds(timeoutSeconds), [&] { return state->done; });

    if (!completed)
        state->result.error = "Timeout waiting for user input";

    auto resultCopy = state->result;
    lock.unlock();

    if (!completed)
        PostEscapeToRhino();

    return resultCopy;
}

} // namespace Rook
