// SceneGraph.cpp
//
// Core scene graph engine implementation.
// Port of C# SceneGraph.cs with per-object CRhinoEventWatcher events
// replacing the full-scene-scan CommandRecorded approach.

#include "stdafx.h"
#include "SceneGraph/SceneGraph.h"
#include "SceneGraph/SceneGraphWatcher.h"
#include "SceneGraph/SceneGraphConduit.h"
#include "Threading/MainThreadDispatcher.h"
#include "Models/DocumentHelpers.h"

#include <algorithm>
#include <cmath>
#include <sstream>
#include <iomanip>
#include <unordered_set>

// ON_RTree is available transitively via stdafx.h → RhinoSdk.h → opennurbs.h

namespace Rook {

// ================================================================
// Singleton & Lifecycle
// ================================================================

CSceneGraph& CSceneGraph::Instance()
{
    static CSceneGraph instance;
    return instance;
}

CSceneGraph::CSceneGraph()
    : m_rtree(std::make_unique<ON_RTree>())
    , m_readSnapshot(std::make_shared<const SceneGraphSnapshot>())
{
    m_activeProfile = BuildGeneralProfile();
}

CSceneGraph::~CSceneGraph()
{
    Stop();
}

void CSceneGraph::Start()
{
    if (m_running.load()) return;
    m_running.store(true);

    // Start background processor thread
    m_processorThread = std::thread(&CSceneGraph::ProcessorLoop, this);

    // Create and register event watcher
    m_watcher = std::make_unique<CSceneGraphWatcher>(*this);
    m_watcher->Register();
    m_watcher->Enable(TRUE);

    // If a document is already open (plugin loaded after file open),
    // trigger an async reconcile so the graph isn't left empty.
    unsigned int sn = CRhinoDoc::TargetDocSerialNumber();
    CRhinoDoc* pDoc = CRhinoDoc::FromRuntimeSerialNumber(sn);
    if (pDoc)
        ReconcileAsync(*pDoc);
}

void CSceneGraph::Stop()
{
    if (!m_running.load()) return;

    // Disable display conduit first (must be on main thread — Stop is called from OnUnloadPlugIn)
    if (m_conduit)
    {
        m_conduit->Disable();
        m_conduit.reset();
    }

    // Disable and unregister event watcher.
    // UnRegister() must be called before reset() — otherwise Rhino's global
    // event dispatch list still holds a vtable pointer to the destroyed
    // CRhinoEventWatcher subclass, and any subsequent event dispatch is a
    // use-after-free. Matches the existing SessionRecorder::Stop pattern.
    if (m_watcher)
    {
        m_watcher->Enable(FALSE);
        m_watcher->UnRegister();
        m_watcher.reset();
    }

    // Signal background thread to exit.
    //
    // m_running=false is the cancellation signal observed by:
    //   - ProcessorLoop's outer while / cv wait (coarse: between batches)
    //   - ProcessEvents / ProcessReconcile  (fine: between iterations)
    //   - RemoveNodesBulk / RemoveEdge      (fine: inside the batch loops)
    //   - PublishSnapshot                    (fine: skips the multi-GB copy)
    //
    // Commit 2 reshaped the hot path: RemoveNodesBulk does one O(|m_edges|)
    // pass regardless of how many nodes are being removed, so the stale-
    // removal loop in ProcessReconcile is no longer O(|m_edges|^2). The
    // cancellation checks remain as a safety net for pathological inputs.
    //
    // Partial state is safe here because:
    //   1. CRookServer has already been stopped in OnUnloadPlugIn before
    //      reaching this point, so no HTTP reader can observe the graph.
    //   2. The singleton's containers are torn down at DLL unload, so the
    //      inconsistency never leaks beyond this process.
    //   3. Stop() is only ever called from the unload path — there is no
    //      restart-after-stop sequence that would reuse the broken state.
    m_running.store(false);
    m_cv.notify_one();

    if (m_processorThread.joinable())
        m_processorThread.join();

    // Drain any remaining events (not processed because thread exited)
    {
        std::lock_guard<std::mutex> lock(m_eventMutex);
        m_eventQueue.clear();
    }
}

// ================================================================
// Event Intake
// ================================================================

void CSceneGraph::EnqueueEvent(ObjectEvent&& event)
{
    {
        std::lock_guard<std::mutex> lock(m_eventMutex);
        m_eventQueue.push_back(std::move(event));
    }
    {
        std::lock_guard<std::mutex> lock(m_cvMutex);
        m_hasPendingWork = true;
    }
    m_cv.notify_one();
}

// ================================================================
// Read API
// ================================================================

std::shared_ptr<const SceneGraphSnapshot> CSceneGraph::ReadSnapshot() const
{
    std::lock_guard<std::mutex> lock(m_snapshotMutex);
    return m_readSnapshot;
}

int CSceneGraph::Sequence() const
{
    return ReadSnapshot()->sequence;
}

int CSceneGraph::NodeCount() const
{
    return static_cast<int>(ReadSnapshot()->nodes.size());
}

int CSceneGraph::EdgeCount() const
{
    return static_cast<int>(ReadSnapshot()->edges.size());
}

// ================================================================
// Mutation API
// ================================================================

// ─── Shared capture helper (must be called on main thread) ────

ReconcileData CSceneGraph::CaptureReconcileData(CRhinoDoc& doc)
{
    ReconcileData data;

    data.unitScale = ON::UnitScale(
        doc.Properties().ModelUnitsAndTolerances().m_unit_system,
        ON::LengthUnitSystem::Meters);

    CRhinoObjectIterator it(doc,
        CRhinoObjectIterator::normal_or_locked_objects,
        CRhinoObjectIterator::active_objects);

    for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
    {
        if (!CSceneGraphWatcher::IsTrackableType(obj->ObjectType()))
            continue;

        ObjectEvent ev;
        ev.type = ObjectEvent::Type::Created;
        ev.id = UuidToString(obj->Attributes().m_uuid);
        ev.name = WideToUtf8(obj->Attributes().m_name);

        int layerIdx = obj->Attributes().m_layer_index;
        if (layerIdx >= 0 && layerIdx < doc.m_layer_table.LayerCount())
        {
            ON_wString lp;
            doc.m_layer_table.GetLayerPathName(layerIdx, lp);
            ev.layerPath = WideToUtf8(lp);
        }

        ev.geometryType = ObjectTypeToString(obj->ObjectType());

        const ON_Geometry* geom = obj->Geometry();
        if (geom)
        {
            ON_BoundingBox bbox = geom->BoundingBox();
            if (bbox.IsValid())
            {
                ev.bboxMin = { bbox.m_min.x, bbox.m_min.y, bbox.m_min.z };
                ev.bboxMax = { bbox.m_max.x, bbox.m_max.y, bbox.m_max.z };
                ev.bboxValid = true;
                ev.unitScale = data.unitScale;
                data.liveObjects.push_back(std::move(ev));
            }
        }
    }
    return data;
}

// ─── Blocking reconcile (HTTP / manual path) ─────────────────

int CSceneGraph::Reconcile()
{
    // Step 1: Capture all objects on main thread via Dispatch
    auto future = CMainThreadDispatcher::Instance().Dispatch([]() -> ReconcileData {
        CRhinoDoc* pDoc = GetDocument();
        if (!pDoc) return {};
        return CaptureReconcileData(*pDoc);
    });

    auto reconcileData = future.get();

    // Step 2: Process on background thread
    auto actionFuture = EnqueueAction([this, data = std::move(reconcileData)]() -> int {
        int changes = ProcessReconcile(data);
        PublishSnapshot();
        return changes;
    });

    return actionFuture.get();
}

// ─── Non-blocking reconcile (watcher / startup path) ─────────

void CSceneGraph::ReconcileAsync(CRhinoDoc& doc)
{
    if (!m_running.load()) return;

    // Capture inline — we are already on the main thread
    auto data = CaptureReconcileData(doc);

    // Fire-and-forget background processing
    auto future = EnqueueAction([this, data = std::move(data)]() {
        ProcessReconcile(data);
        PublishSnapshot();
    });
    (void)future;  // Explicitly discard — fire-and-forget
}

// ─── Non-blocking clear (watcher close path) ─────────────────

void CSceneGraph::ClearAsync()
{
    if (!m_running.load()) return;

    // Drop any queued events first. OnCloseDocument typically arrives
    // after a flood of per-object OnDeleteObject callbacks from Rhino,
    // each of which enqueued a Deleted ObjectEvent. Processing those
    // events one-by-one through RemoveNodeInternal is the O(|edges|^2)
    // hotspot observed on large-file close — and they refer to a doc
    // that's being cleared anyway, so the work is pure waste.
    //
    // Clearing the event queue here means the processor's next drain
    // will skip straight to the ClearInternal action below.
    {
        std::lock_guard<std::mutex> lock(m_eventMutex);
        m_eventQueue.clear();
    }

    auto future = EnqueueAction([this]() { ClearInternal(); });
    (void)future;  // Explicitly discard — fire-and-forget
}

void CSceneGraph::SetProfile(DomainProfile profile)
{
    auto future = EnqueueAction([this, p = std::move(profile)]() mutable {
        m_activeProfile = std::move(p);
        for (auto& [id, node] : m_nodes)
            Classify(node);
        PublishSnapshot();
    });
    future.get();
}

int CSceneGraph::Reclassify(const std::vector<std::string>* objectIds)
{
    // Copy IDs if provided (they may go out of scope before bg thread runs)
    std::vector<std::string> idsCopy;
    bool filterByIds = false;
    if (objectIds && !objectIds->empty())
    {
        idsCopy = *objectIds;
        filterByIds = true;
    }

    auto future = EnqueueAction([this, ids = std::move(idsCopy), filterByIds]() -> int {
        int count = 0;
        if (filterByIds)
        {
            for (const auto& id : ids)
            {
                auto it = m_nodes.find(id);
                if (it != m_nodes.end())
                {
                    Classify(it->second);
                    count++;
                }
            }
        }
        else
        {
            for (auto& [id, node] : m_nodes)
            {
                Classify(node);
                count++;
            }
        }
        PublishSnapshot();
        return count;
    });
    return future.get();
}

void CSceneGraph::Clear()
{
    auto future = EnqueueAction([this]() { ClearInternal(); });
    future.get();
}

// ─── Shared clear logic (background thread only) ─────────────

void CSceneGraph::ClearInternal()
{
    m_nodes.clear();
    m_edges.clear();
    m_edgesByNode.clear();
    m_rtree = std::make_unique<ON_RTree>();
    m_rtreeIdOrder.clear();
    // Flush any pending events so stale events don't survive a clear
    {
        std::lock_guard<std::mutex> lock(m_eventMutex);
        m_eventQueue.clear();
    }
    {
        std::lock_guard<std::mutex> lock(m_diffMutex);
        m_addedBySeq.clear();
        m_removedBySeq.clear();
        m_modifiedBySeq.clear();
        m_addedEdgesBySeq.clear();
        m_removedEdgesBySeq.clear();
        m_sequence = 0;
    }
    PublishSnapshot();
}

// ================================================================
// Diff API
// ================================================================

SceneGraphDiff CSceneGraph::GetDiff(int sinceSequence) const
{
    std::lock_guard<std::mutex> lock(m_diffMutex);
    SceneGraphDiff diff;
    diff.currentSequence = m_sequence;

    // Detect if requested range exceeds available history (pruned at 500)
    const int maxHistory = 500;
    if (sinceSequence < m_sequence - maxHistory)
        diff.truncated = true;

    for (int seq = sinceSequence + 1; seq <= m_sequence; seq++)
    {
        auto ait = m_addedBySeq.find(seq);
        if (ait != m_addedBySeq.end())
            diff.addedNodes.insert(diff.addedNodes.end(), ait->second.begin(), ait->second.end());

        auto rit = m_removedBySeq.find(seq);
        if (rit != m_removedBySeq.end())
            diff.removedNodeIds.insert(diff.removedNodeIds.end(), rit->second.begin(), rit->second.end());

        auto mit = m_modifiedBySeq.find(seq);
        if (mit != m_modifiedBySeq.end())
            diff.modifiedNodes.insert(diff.modifiedNodes.end(), mit->second.begin(), mit->second.end());

        auto aeit = m_addedEdgesBySeq.find(seq);
        if (aeit != m_addedEdgesBySeq.end())
            diff.addedEdges.insert(diff.addedEdges.end(), aeit->second.begin(), aeit->second.end());

        auto reit = m_removedEdgesBySeq.find(seq);
        if (reit != m_removedEdgesBySeq.end())
            diff.removedEdges.insert(diff.removedEdges.end(), reit->second.begin(), reit->second.end());
    }

    return diff;
}

std::string CSceneGraph::GetNodeSummary(const std::string& objectId,
    std::shared_ptr<const SceneGraphSnapshot> existingSnap) const
{
    auto snap = existingSnap ? existingSnap : ReadSnapshot();
    auto nodeIt = snap->nodes.find(objectId);
    if (nodeIt == snap->nodes.end())
        return "Object '" + objectId + "' not found in scene graph.";

    const auto& node = nodeIt->second;
    std::string label = node.domainLabel.empty() ? node.shapeClass : node.domainLabel;

    std::ostringstream oss;
    // Uppercase label
    std::string upperLabel = label;
    for (auto& c : upperLabel) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));

    oss << upperLabel << " '" << node.name << "' (" << node.shapeClass
        << ", " << std::fixed << std::setprecision(1)
        << node.metrics.maxDim << " x " << node.metrics.midDim << " x " << node.metrics.minDim << ")";

    auto edgeIt = snap->edgesByNode.find(objectId);
    if (edgeIt != snap->edgesByNode.end() && !edgeIt->second.empty())
    {
        std::vector<std::string> parts;
        int count = 0;
        for (const auto& edge : edgeIt->second)
        {
            if (count++ >= 10) break;
            std::string otherId = (edge.sourceId == objectId) ? edge.targetId : edge.sourceId;
            std::string otherLabel = "unknown";
            auto otherIt = snap->nodes.find(otherId);
            if (otherIt != snap->nodes.end())
            {
                const auto& other = otherIt->second;
                otherLabel = other.domainLabel.empty() ? other.shapeClass : other.domainLabel;
            }
            std::string upperOther = otherLabel;
            for (auto& c : upperOther) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));

            std::string otherName = (otherIt != snap->nodes.end()) ? otherIt->second.name : otherId;

            if (edge.sourceId == objectId)
                parts.push_back(edge.relationship + ": " + upperOther + " '" + otherName + "'");
            else
                parts.push_back(InverseRelationship(edge.relationship) + " from: " + upperOther + " '" + otherName + "'");
        }

        oss << " -- ";
        for (size_t i = 0; i < parts.size(); i++)
        {
            if (i > 0) oss << ", ";
            oss << parts[i];
        }
    }

    return oss.str();
}

// ================================================================
// Background Processing
// ================================================================

void CSceneGraph::ProcessorLoop()
{
    while (m_running.load())
    {
        // Wait for events or actions (with 100ms timeout for natural batching)
        {
            std::unique_lock<std::mutex> lock(m_cvMutex);
            m_cv.wait_for(lock, std::chrono::milliseconds(100), [this]() {
                return m_hasPendingWork || !m_running.load();
            });
            m_hasPendingWork = false;
        }

        if (!m_running.load()) break;

        // Drain events (swap-and-process pattern)
        std::vector<ObjectEvent> events;
        {
            std::lock_guard<std::mutex> lock(m_eventMutex);
            std::swap(events, m_eventQueue);
        }

        bool publishNeeded = false;
        if (!events.empty())
        {
            try
            {
                ProcessEvents(events);
                publishNeeded = true;
            }
            catch (...)
            {
                // Log and continue — don't let one bad batch kill the background thread.
                // All subsequent EnqueueAction futures would block forever if we exit.
            }
        }

        if (publishNeeded)
        {
            try { PublishSnapshot(); }
            catch (...) {}
        }

        // Drain action queue
        std::queue<std::function<void()>> actions;
        {
            std::lock_guard<std::mutex> lock(m_actionMutex);
            std::swap(actions, m_actionQueue);
        }
        while (!actions.empty())
        {
            try { actions.front()(); }
            catch (...) {}
            actions.pop();
        }
    }

    // On exit, drain remaining actions so blocked futures resolve
    std::queue<std::function<void()>> remaining;
    {
        std::lock_guard<std::mutex> lock(m_actionMutex);
        std::swap(remaining, m_actionQueue);
    }
    while (!remaining.empty())
    {
        try { remaining.front()(); }
        catch (...) {}
        remaining.pop();
    }
}

void CSceneGraph::ProcessEvents(std::vector<ObjectEvent>& batch)
{
    bool needsRTreeRebuild = false;
    // Store IDs instead of raw pointers — unordered_map rehash invalidates pointers
    std::vector<std::string> createdIds;

    // Modified nodes: store ID + old edges removed during update
    struct ModifiedInfo { std::string id; std::vector<SceneEdge> oldEdges; };
    std::vector<ModifiedInfo> modifiedInfos;

    // Deleted nodes are collected here and removed in one batch after the
    // pass — a delete-flood (from e.g. Select All + Delete, or the flood
    // Rhino fires during document close) was the second-order hotspot for
    // the Rhino.DMP 2026-04-07 unload hang, alongside ProcessReconcile's
    // stale-removal loop.
    std::vector<std::string> deletedIds;

    // Pass 1: Insert/delete/modify nodes (NO relationship computation here)
    //
    // Shutdown preemption: we check m_running between iterations and return
    // early if Stop() was called. The graph is being torn down, so leaving
    // m_nodes / m_edges in a partially-reconciled state is acceptable — no
    // reader will observe it (the HTTP server has already been stopped in
    // OnUnloadPlugIn before reaching CSceneGraph::Stop()).
    for (auto& ev : batch)
    {
        if (!m_running.load(std::memory_order_relaxed)) return;

        if (ev.unitScale > 0)
            m_cachedUnitScale = ev.unitScale;

        switch (ev.type)
        {
        case ObjectEvent::Type::Created:
        {
            if (m_nodes.count(ev.id)) continue;
            if (!ev.bboxValid) continue;
            auto node = BuildNodeFromEvent(ev);
            std::string id = node.id;
            m_nodes[id] = std::move(node);
            Classify(m_nodes[id]);
            createdIds.push_back(id);
            needsRTreeRebuild = true;
            break;
        }
        case ObjectEvent::Type::Deleted:
            if (m_nodes.count(ev.id))
            {
                // Defer the actual removal — collect the id here and
                // call RemoveNodesBulk once after the loop so a batch
                // of deletes costs O(|m_edges|) instead of N passes.
                deletedIds.push_back(ev.id);
                needsRTreeRebuild = true;
            }
            break;

        case ObjectEvent::Type::Modified:
            if (ev.bboxValid)
            {
                auto oldEdges = UpdateNodeFromEvent(ev);
                modifiedInfos.push_back({ ev.id, std::move(oldEdges) });
                needsRTreeRebuild = true;
            }
            break;
        }
    }

    if (!m_running.load(std::memory_order_relaxed)) return;

    // Apply the batched delete removal now that Pass 1 is complete.
    if (!deletedIds.empty())
        RemoveNodesBulk(deletedIds);

    if (!m_running.load(std::memory_order_relaxed)) return;

    // Rebuild RTree with ALL current nodes before computing relationships
    if (needsRTreeRebuild)
        RebuildRTree();

    // Pass 2: Compute relationships for new AND modified nodes (RTree now has all nodes).
    // Re-lookup by ID to get stable references (safe after all insertions complete).
    for (const auto& id : createdIds)
    {
        if (!m_running.load(std::memory_order_relaxed)) return;

        auto it = m_nodes.find(id);
        if (it == m_nodes.end()) continue;
        const auto& node = it->second;

        auto newEdges = (node.metrics.volume > 0.0001)
            ? ComputeRelationships(node)
            : std::vector<SceneEdge>{};
        for (const auto& edge : newEdges)
            AddEdge(edge);

        TrackChange(&node, nullptr, nullptr,
                    newEdges.empty() ? nullptr : &newEdges, nullptr);
    }

    for (auto& mod : modifiedInfos)
    {
        if (!m_running.load(std::memory_order_relaxed)) return;

        auto it = m_nodes.find(mod.id);
        if (it == m_nodes.end()) continue;
        const auto& node = it->second;

        auto newEdges = (node.metrics.volume > 0.0001)
            ? ComputeRelationships(node)
            : std::vector<SceneEdge>{};
        for (const auto& edge : newEdges)
            AddEdge(edge);

        TrackChange(nullptr, &node, nullptr,
                    newEdges.empty() ? nullptr : &newEdges,
                    mod.oldEdges.empty() ? nullptr : &mod.oldEdges);
    }
}

int CSceneGraph::ProcessReconcile(const ReconcileData& data)
{
    m_cachedUnitScale = data.unitScale;
    int changes = 0;
    std::set<std::string> liveIds;
    // Store IDs instead of raw pointers — unordered_map rehash invalidates pointers
    std::vector<std::string> newNodeIds;

    // Modified nodes: store ID + old edges removed during update
    struct ModifiedInfo { std::string id; std::vector<SceneEdge> oldEdges; };
    std::vector<ModifiedInfo> modifiedInfos;

    // Pass 1: Insert new, update changed, track live IDs (NO relationship computation)
    //
    // Shutdown preemption: checks are placed between iterations so that a
    // long reconcile on a large file can abort quickly when Stop() is called
    // during plugin unload. Partial reconcile state is acceptable on
    // shutdown — see CSceneGraph::Stop() for the rationale.
    for (const auto& ev : data.liveObjects)
    {
        if (!m_running.load(std::memory_order_relaxed)) return changes;

        liveIds.insert(ev.id);

        auto it = m_nodes.find(ev.id);
        if (it == m_nodes.end())
        {
            auto node = BuildNodeFromEvent(ev);
            std::string id = node.id;
            m_nodes[id] = std::move(node);
            Classify(m_nodes[id]);
            newNodeIds.push_back(id);
            changes++;
        }
        else
        {
            // Check if bbox changed
            auto& existing = it->second;
            if (std::abs(ev.bboxMin[0] - existing.bboxMin[0]) > 0.001 ||
                std::abs(ev.bboxMin[1] - existing.bboxMin[1]) > 0.001 ||
                std::abs(ev.bboxMin[2] - existing.bboxMin[2]) > 0.001 ||
                std::abs(ev.bboxMax[0] - existing.bboxMax[0]) > 0.001 ||
                std::abs(ev.bboxMax[1] - existing.bboxMax[1]) > 0.001 ||
                std::abs(ev.bboxMax[2] - existing.bboxMax[2]) > 0.001)
            {
                auto oldEdges = UpdateNodeFromEvent(ev);
                modifiedInfos.push_back({ ev.id, std::move(oldEdges) });
                changes++;
            }
        }
    }

    if (!m_running.load(std::memory_order_relaxed)) return changes;

    // Remove stale nodes. Three cases:
    //   (a) nothing stale → skip
    //   (b) all nodes stale → ClearInternal fast path (O(|nodes|+|edges|)
    //       for the container clears, no per-node work)
    //   (c) partial stale → RemoveNodesBulk with a single-pass filter
    //
    // Before commit 2 this was a per-node RemoveNodeInternal loop which
    // degraded to O(|m_edges|^2) on large graphs — the root cause of
    // the Rhino.DMP 2026-04-07 unload hang.
    std::vector<std::string> staleIds;
    for (const auto& [id, node] : m_nodes)
    {
        if (liveIds.find(id) == liveIds.end())
            staleIds.push_back(id);
    }

    if (!staleIds.empty())
    {
        if (staleIds.size() == m_nodes.size())
        {
            // Entire graph is stale (typical for a document switch or
            // reconcile-after-close). Collapse to ClearInternal and
            // rebuild fresh nodes on the second pass. Much cheaper than
            // per-node removal even with the batch path.
            const int cleared = static_cast<int>(m_nodes.size());
            ClearInternal();
            changes += cleared;
            // newNodeIds / modifiedInfos collected in Pass 1 now point
            // into m_nodes entries that were just cleared. The create
            // branch of Pass 1 only pushed new nodes, which we also just
            // wiped — so Pass 2 below must be skipped. Return the
            // change count; subsequent reconciles will rebuild.
            return changes;
        }

        RemoveNodesBulk(staleIds);
        changes += static_cast<int>(staleIds.size());
    }

    if (!m_running.load(std::memory_order_relaxed)) return changes;

    // Rebuild RTree
    if (changes > 0)
        RebuildRTree();

    // Pass 2: Compute relationships for new AND modified nodes (RTree now current)
    for (const auto& id : newNodeIds)
    {
        if (!m_running.load(std::memory_order_relaxed)) return changes;

        auto it = m_nodes.find(id);
        if (it == m_nodes.end()) continue;
        const auto& node = it->second;

        auto newEdges = (node.metrics.volume > 0.0001)
            ? ComputeRelationships(node)
            : std::vector<SceneEdge>{};
        for (const auto& edge : newEdges)
            AddEdge(edge);

        TrackChange(&node, nullptr, nullptr,
                    newEdges.empty() ? nullptr : &newEdges, nullptr);
    }

    for (auto& mod : modifiedInfos)
    {
        if (!m_running.load(std::memory_order_relaxed)) return changes;

        auto it = m_nodes.find(mod.id);
        if (it == m_nodes.end()) continue;
        const auto& node = it->second;

        auto newEdges = (node.metrics.volume > 0.0001)
            ? ComputeRelationships(node)
            : std::vector<SceneEdge>{};
        for (const auto& edge : newEdges)
            AddEdge(edge);

        TrackChange(nullptr, &node, nullptr,
                    newEdges.empty() ? nullptr : &newEdges,
                    mod.oldEdges.empty() ? nullptr : &mod.oldEdges);
    }

    return changes;
}

// ================================================================
// Node Operations
// ================================================================

SceneNode CSceneGraph::BuildNodeFromEvent(const ObjectEvent& ev)
{
    SceneNode node;
    node.id = ev.id;
    node.name = ev.name;
    node.layer = ev.layerPath;
    node.geometryType = ev.geometryType;
    node.bboxMin = ev.bboxMin;
    node.bboxMax = ev.bboxMax;
    node.metrics = ComputeMetrics(ev.bboxMin, ev.bboxMax);
    return node;
}

std::vector<SceneEdge> CSceneGraph::UpdateNodeFromEvent(const ObjectEvent& ev)
{
    auto it = m_nodes.find(ev.id);
    if (it == m_nodes.end()) return {};

    auto& existing = it->second;

    // Preserve provenance
    std::string createdBy = existing.createdBy;
    std::string creationIntent = existing.creationIntent;
    std::string creationCommand = existing.creationCommand;
    int sessionSequence = existing.sessionSequence;

    // Rebuild node with new geometry
    SceneNode updated = BuildNodeFromEvent(ev);
    updated.createdBy = createdBy;
    updated.creationIntent = creationIntent;
    updated.creationCommand = creationCommand;
    updated.sessionSequence = sessionSequence;
    Classify(updated);

    // Remove old edges for this node
    std::vector<SceneEdge> oldEdges;
    auto edgeIt = m_edgesByNode.find(ev.id);
    if (edgeIt != m_edgesByNode.end())
        oldEdges = edgeIt->second;  // copy

    for (const auto& edge : oldEdges)
        RemoveEdge(edge.sourceId, edge.targetId, edge.relationship);

    m_nodes[ev.id] = std::move(updated);

    // Relationship computation and TrackChange are deferred to the caller
    // (after RTree rebuild), so that ComputeRelationships uses up-to-date spatial index.
    return oldEdges;
}

void CSceneGraph::RemoveNodesBulk(const std::vector<std::string>& ids)
{
    // Batch node removal with a single pass over m_edges.
    //
    // The old RemoveNodeInternal did one std::remove_if over m_edges per
    // removed edge, per removed node — O(|ids| * avg_degree * |m_edges|),
    // which collapsed to O(|m_edges|^2) on large graphs. On an 8.5 GB
    // working-set file this produced an effectively unbounded hang on
    // close; see project_scene_graph_teardown_hang.md.
    //
    // The new algorithm is O(|m_edges| + sum(degree of neighbors)):
    //   1. Collect edges to remove into removedPerNode for TrackChange.
    //   2. ONE pass over m_edges with set-membership predicate.
    //   3. For each unique neighbor (not being removed), one pass over
    //      that neighbor's edge list. This is bounded by total edges.
    //   4. Erase nodes from m_nodes and emit per-node diffs.
    if (ids.empty()) return;
    if (!m_running.load(std::memory_order_relaxed)) return;

    std::unordered_set<std::string> idSet(ids.begin(), ids.end());

    // Step 1: gather per-node removed edges and detach from m_edgesByNode.
    struct RemovedEntry { std::string id; std::vector<SceneEdge> edges; };
    std::vector<RemovedEntry> removedPerNode;
    removedPerNode.reserve(ids.size());

    for (const auto& id : ids)
    {
        if (m_nodes.find(id) == m_nodes.end()) continue;

        RemovedEntry entry;
        entry.id = id;

        auto edgeIt = m_edgesByNode.find(id);
        if (edgeIt != m_edgesByNode.end())
        {
            entry.edges = std::move(edgeIt->second);
            m_edgesByNode.erase(edgeIt);
        }

        removedPerNode.push_back(std::move(entry));
    }

    if (removedPerNode.empty()) return;

    if (!m_running.load(std::memory_order_relaxed)) return;

    // Step 2: single-pass filter over the global edge list.
    // Any edge touching a removed node — as source or target — is dropped.
    auto touchesRemoved = [&idSet](const SceneEdge& e) {
        return idSet.find(e.sourceId) != idSet.end()
            || idSet.find(e.targetId) != idSet.end();
    };
    m_edges.erase(
        std::remove_if(m_edges.begin(), m_edges.end(), touchesRemoved),
        m_edges.end());

    if (!m_running.load(std::memory_order_relaxed)) return;

    // Step 3: filter neighbor edge lists. We only touch nodes that
    // actually had an edge into a removed node; other entries in
    // m_edgesByNode are untouched.
    std::unordered_set<std::string> visitedNeighbors;
    for (const auto& entry : removedPerNode)
    {
        for (const auto& edge : entry.edges)
        {
            const std::string& otherId =
                (edge.sourceId == entry.id) ? edge.targetId : edge.sourceId;

            // Skip if the neighbor is also being removed (its entry was
            // already erased above) or we've already scrubbed it.
            if (idSet.find(otherId) != idSet.end()) continue;
            if (!visitedNeighbors.insert(otherId).second) continue;

            if (!m_running.load(std::memory_order_relaxed)) return;

            auto neighborIt = m_edgesByNode.find(otherId);
            if (neighborIt == m_edgesByNode.end()) continue;

            auto& neighborEdges = neighborIt->second;
            neighborEdges.erase(
                std::remove_if(neighborEdges.begin(), neighborEdges.end(), touchesRemoved),
                neighborEdges.end());
        }
    }

    if (!m_running.load(std::memory_order_relaxed)) return;

    // Step 4: erase nodes from m_nodes and emit per-node diff entries.
    // Per-node TrackChange is kept (rather than a single batch diff) so
    // the diff API's sequence semantics are preserved — each removed
    // node still gets its own sequence number for GetDiff() consumers.
    for (auto& entry : removedPerNode)
    {
        m_nodes.erase(entry.id);
        TrackChange(nullptr, nullptr, &entry.id, nullptr,
                    entry.edges.empty() ? nullptr : &entry.edges);
    }
}

// ComputeMetrics has been extracted to Infrastructure/ShapeMetrics.h

// ================================================================
// Classification
// ================================================================

void CSceneGraph::Classify(SceneNode& node)
{
    node.shapeClass = DetermineShapeClass(node.metrics);

    std::string bestLabel;
    int bestPriority = -1;
    double bestConfidence = 0.5;

    for (const auto& rule : m_activeProfile.rules)
    {
        if (rule.priority <= bestPriority) continue;
        if (!rule.shapeClass.empty() && rule.shapeClass != node.shapeClass) continue;
        if (!MatchesRule(node.metrics, rule)) continue;

        bestLabel = rule.label;
        bestPriority = rule.priority;
        bestConfidence = ComputeRuleConfidence(node.metrics, rule);
    }

    node.domainLabel = bestLabel;
    node.classConfidence = bestConfidence;
}

// DetermineShapeClass has been extracted to Infrastructure/ShapeMetrics.h

bool CSceneGraph::MatchesRule(const ShapeMetrics& m, const ClassificationRule& rule)
{
    if (rule.minElongation && m.elongation < *rule.minElongation) return false;
    if (rule.maxElongation && m.elongation > *rule.maxElongation) return false;
    if (rule.minFlatness && m.flatness < *rule.minFlatness) return false;
    if (rule.maxFlatness && m.flatness > *rule.maxFlatness) return false;
    if (rule.maxThinness && m.thinness > *rule.maxThinness) return false;
    if (rule.minHeight && (m.topZ - m.baseZ) < *rule.minHeight) return false;
    if (rule.mustBeVertical && *rule.mustBeVertical && !m.isVertical) return false;
    if (rule.mustBeHorizontal && *rule.mustBeHorizontal && !m.isHorizontal) return false;
    return true;
}

double CSceneGraph::ComputeRuleConfidence(const ShapeMetrics& m, const ClassificationRule& rule)
{
    int total = 0, met = 0;
    if (!rule.shapeClass.empty()) { total++; met++; }
    if (rule.mustBeVertical) { total++; met++; }
    if (rule.mustBeHorizontal) { total++; met++; }
    if (rule.minElongation) { total++; if (m.elongation >= *rule.minElongation) met++; }
    if (rule.maxElongation) { total++; if (m.elongation <= *rule.maxElongation) met++; }
    if (rule.minFlatness) { total++; if (m.flatness >= *rule.minFlatness) met++; }
    if (rule.maxFlatness) { total++; if (m.flatness <= *rule.maxFlatness) met++; }
    if (rule.maxThinness) { total++; if (m.thinness <= *rule.maxThinness) met++; }
    if (rule.minHeight) { total++; if ((m.topZ - m.baseZ) >= *rule.minHeight) met++; }

    if (total == 0) return 0.5;
    double ratio = static_cast<double>(met) / total;
    return 0.5 + (0.45 * ratio * (std::min)(static_cast<double>(total) / 4.0, 1.0));
}

// ================================================================
// Spatial Relationships
// ================================================================

std::vector<SceneEdge> CSceneGraph::ComputeRelationships(const SceneNode& node)
{
    std::vector<SceneEdge> results;
    auto neighborIds = FindNeighborIds(node);
    double unitScale = m_cachedUnitScale > 0 ? m_cachedUnitScale : 1.0;

    for (const auto& neighborId : neighborIds)
    {
        if (neighborId == node.id) continue;
        auto it = m_nodes.find(neighborId);
        if (it == m_nodes.end()) continue;
        if (it->second.metrics.volume < 0.0001) continue;
        if (HasEdge(node.id, neighborId)) continue;

        auto edges = ComputePairRelationships(node, it->second, unitScale);
        results.insert(results.end(), edges.begin(), edges.end());
    }

    return results;
}

std::vector<SceneEdge> CSceneGraph::ComputePairRelationships(
    const SceneNode& a, const SceneNode& b, double unitScale)
{
    std::vector<SceneEdge> results;

    double dist = BBoxDistance(a.bboxMin, a.bboxMax, b.bboxMin, b.bboxMax);
    double overlapVol = BBoxOverlapVolume(a.bboxMin, a.bboxMax, b.bboxMin, b.bboxMax);
    std::string direction = ComputeDirection(a, b);

    // Tier 1: Topological
    if (BBoxContains(a.bboxMin, a.bboxMax, b.bboxMin, b.bboxMax))
    {
        results.push_back({ a.id, b.id, "contains", 0, overlapVol, direction });
        return results;
    }
    if (BBoxContains(b.bboxMin, b.bboxMax, a.bboxMin, a.bboxMax))
    {
        results.push_back({ b.id, a.id, "contains", 0, overlapVol, InverseDirection(direction) });
        return results;
    }
    if (overlapVol > 0)
    {
        results.push_back({ a.id, b.id, "intersects", 0, overlapVol, direction });
    }

    // Tier 2: Proximity
    double tolerance = 0.05 * unitScale;

    // Supports: A's top ~ B's base with >= 50% horizontal overlap
    if (std::abs(a.metrics.topZ - b.metrics.baseZ) < tolerance)
    {
        double hOverlap = HorizontalOverlapFraction(a.bboxMin, a.bboxMax, b.bboxMin, b.bboxMax);
        if (hOverlap > 0.5)
        {
            results.push_back({ a.id, b.id, "supports",
                std::abs(a.metrics.topZ - b.metrics.baseZ), hOverlap, "above" });
        }
    }
    else if (std::abs(b.metrics.topZ - a.metrics.baseZ) < tolerance)
    {
        double hOverlap = HorizontalOverlapFraction(b.bboxMin, b.bboxMax, a.bboxMin, a.bboxMax);
        if (hOverlap > 0.5)
        {
            results.push_back({ b.id, a.id, "supports",
                std::abs(b.metrics.topZ - a.metrics.baseZ), hOverlap, "above" });
        }
    }

    // Adjacent: close but not overlapping
    if (dist > 0 && dist < tolerance * 4 && overlapVol == 0)
    {
        results.push_back({ a.id, b.id, "adjacent", dist, 0, direction });
    }

    // Above/Below: vertical relationship without support
    bool hasSupports = false;
    for (const auto& e : results)
    {
        if (e.relationship == "supports") { hasSupports = true; break; }
    }

    if (!hasSupports)
    {
        double hOverlap = HorizontalOverlapFraction(a.bboxMin, a.bboxMax, b.bboxMin, b.bboxMax);
        if (hOverlap > 0.3)
        {
            if (a.metrics.centroidZ > b.metrics.centroidZ + tolerance)
                results.push_back({ a.id, b.id, "above", dist, 0, "above" });
            else if (b.metrics.centroidZ > a.metrics.centroidZ + tolerance)
                results.push_back({ b.id, a.id, "above", dist, 0, "above" });
        }
    }

    // Tier 3: Near (fallback)
    if (results.empty() && dist > 0 && dist < m_proximityThreshold * unitScale)
    {
        results.push_back({ a.id, b.id, "near", dist, 0, direction });
    }

    return results;
}

// ================================================================
// RTree
// ================================================================

void CSceneGraph::RebuildRTree()
{
    m_rtree = std::make_unique<ON_RTree>();
    m_rtreeIdOrder.clear();

    for (const auto& [id, node] : m_nodes)
    {
        double aMin[3] = { node.bboxMin[0], node.bboxMin[1], node.bboxMin[2] };
        double aMax[3] = { node.bboxMax[0], node.bboxMax[1], node.bboxMax[2] };
        int index = static_cast<int>(m_rtreeIdOrder.size());
        m_rtreeIdOrder.push_back(id);
        m_rtree->Insert(aMin, aMax, index);
    }
}

std::vector<std::string> CSceneGraph::FindNeighborIds(const SceneNode& node)
{
    double unitScale = m_cachedUnitScale > 0 ? m_cachedUnitScale : 1.0;
    double searchRadius = m_proximityThreshold * unitScale;
    double cx = (node.bboxMin[0] + node.bboxMax[0]) / 2.0;
    double cy = (node.bboxMin[1] + node.bboxMax[1]) / 2.0;
    double cz = (node.bboxMin[2] + node.bboxMax[2]) / 2.0;
    double r = searchRadius + node.metrics.maxDim;

    double sMin[3] = { cx - r, cy - r, cz - r };
    double sMax[3] = { cx + r, cy + r, cz + r };

    // Use the ON_SimpleArray<int> variant — returns integer IDs directly
    ON_SimpleArray<int> rtreeResults;
    m_rtree->Search(sMin, sMax, rtreeResults);

    std::vector<std::string> found;
    found.reserve(rtreeResults.Count());
    for (int i = 0; i < rtreeResults.Count(); ++i)
    {
        int idx = rtreeResults[i];
        if (idx >= 0 && idx < static_cast<int>(m_rtreeIdOrder.size()))
            found.push_back(m_rtreeIdOrder[idx]);
    }
    return found;
}

// ================================================================
// Candidate Query (exact-adjacency refinement)
// ================================================================
//
// Processor-thread-safe lazy candidate query. The body runs entirely inside
// EnqueueAction (i.e. on the processor thread) so m_rtree / m_rtreeIdOrder /
// m_nodes are only ever touched from their owning thread. We score every RTree
// neighbor (self excluded), deterministically sort, then cap — never relying on
// the nondeterministic RTree iteration order.

std::future<CandidateQueryResult>
CSceneGraph::QueryCandidatesAsync(const std::string& objectId, const CandidateQueryOptions& opts)
{
    return EnqueueAction([this, objectId, opts]() -> CandidateQueryResult {
        CandidateQueryResult result;
        result.graphSequence = 0;
        result.sourceFound = false;
        result.capped = false;
        result.totalCandidateCount = 0;

        // m_sequence is protected by m_diffMutex (not atomic). Read it under the
        // lock, then release before touching the RTree.
        {
            std::lock_guard<std::mutex> lk(m_diffMutex);
            result.graphSequence = m_sequence;
        }

        auto it = m_nodes.find(objectId);
        if (it == m_nodes.end())
            return result;                 // sourceFound stays false
        result.sourceFound = true;
        result.sourceNode = it->second;    // plain copy

        if (!m_rtree)
            return result;                 // empty scene guard

        // Gather RTree neighbors (FindNeighborIds includes the source itself).
        std::vector<ScoredCandidate> scored;
        for (const std::string& nid : FindNeighborIds(result.sourceNode))
        {
            if (nid == objectId)
                continue;                  // exclude self
            auto nit = m_nodes.find(nid);
            if (nit == m_nodes.end())
                continue;
            const SceneNode& nb = nit->second;
            ScoredCandidate sc;
            sc.id = nid;
            sc.bboxDistance = BBoxDistance(result.sourceNode.bboxMin, result.sourceNode.bboxMax,
                                           nb.bboxMin, nb.bboxMax);
            sc.bboxOverlap  = BBoxOverlapVolume(result.sourceNode.bboxMin, result.sourceNode.bboxMax,
                                                nb.bboxMin, nb.bboxMax);
            scored.push_back(std::move(sc));
        }

        result.totalCandidateCount = static_cast<int>(scored.size());

        // Deterministic total order: bboxDistance asc, bboxOverlap desc, id asc.
        // (== on doubles is intentional in the tie-break chain — exact-equal
        // scores fall through to the id tie-break, which is fully deterministic.)
        std::sort(scored.begin(), scored.end(),
            [](const ScoredCandidate& a, const ScoredCandidate& b) {
                if (a.bboxDistance != b.bboxDistance) return a.bboxDistance < b.bboxDistance;
                if (a.bboxOverlap  != b.bboxOverlap)  return a.bboxOverlap  > b.bboxOverlap;
                return a.id < b.id;
            });

        // Cap AFTER sorting so the retained set is the deterministic nearest-first prefix.
        int limit = opts.maxCandidates > 0 ? opts.maxCandidates : 64;
        if (result.totalCandidateCount > limit)
        {
            result.capped = true;
            scored.resize(static_cast<size_t>(limit));
        }
        result.candidates = std::move(scored);
        return result;
    });
}

// ================================================================
// Geometry Helpers
// ================================================================

double CSceneGraph::BBoxDistance(
    const std::array<double,3>& aMin, const std::array<double,3>& aMax,
    const std::array<double,3>& bMin, const std::array<double,3>& bMax)
{
    double dx = (std::max)(0.0, (std::max)(aMin[0] - bMax[0], bMin[0] - aMax[0]));
    double dy = (std::max)(0.0, (std::max)(aMin[1] - bMax[1], bMin[1] - aMax[1]));
    double dz = (std::max)(0.0, (std::max)(aMin[2] - bMax[2], bMin[2] - aMax[2]));
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

double CSceneGraph::BBoxOverlapVolume(
    const std::array<double,3>& aMin, const std::array<double,3>& aMax,
    const std::array<double,3>& bMin, const std::array<double,3>& bMax)
{
    double ox = (std::max)(0.0, (std::min)(aMax[0], bMax[0]) - (std::max)(aMin[0], bMin[0]));
    double oy = (std::max)(0.0, (std::min)(aMax[1], bMax[1]) - (std::max)(aMin[1], bMin[1]));
    double oz = (std::max)(0.0, (std::min)(aMax[2], bMax[2]) - (std::max)(aMin[2], bMin[2]));
    return ox * oy * oz;
}

bool CSceneGraph::BBoxContains(
    const std::array<double,3>& outerMin, const std::array<double,3>& outerMax,
    const std::array<double,3>& innerMin, const std::array<double,3>& innerMax)
{
    return outerMin[0] <= innerMin[0] && outerMin[1] <= innerMin[1] && outerMin[2] <= innerMin[2] &&
           outerMax[0] >= innerMax[0] && outerMax[1] >= innerMax[1] && outerMax[2] >= innerMax[2];
}

double CSceneGraph::HorizontalOverlapFraction(
    const std::array<double,3>& aMin, const std::array<double,3>& aMax,
    const std::array<double,3>& bMin, const std::array<double,3>& bMax)
{
    double ox = (std::max)(0.0, (std::min)(aMax[0], bMax[0]) - (std::max)(aMin[0], bMin[0]));
    double oy = (std::max)(0.0, (std::min)(aMax[1], bMax[1]) - (std::max)(aMin[1], bMin[1]));
    double areaOverlap = ox * oy;
    double areaA = (aMax[0] - aMin[0]) * (aMax[1] - aMin[1]);
    double areaB = (bMax[0] - bMin[0]) * (bMax[1] - bMin[1]);
    double minArea = (std::min)(areaA, areaB);
    return minArea > 0 ? areaOverlap / minArea : 0;
}

std::string CSceneGraph::ComputeDirection(const SceneNode& a, const SceneNode& b)
{
    double dx = (b.bboxMin[0] + b.bboxMax[0]) / 2.0 - (a.bboxMin[0] + a.bboxMax[0]) / 2.0;
    double dy = (b.bboxMin[1] + b.bboxMax[1]) / 2.0 - (a.bboxMin[1] + a.bboxMax[1]) / 2.0;
    double dz = (b.bboxMin[2] + b.bboxMax[2]) / 2.0 - (a.bboxMin[2] + a.bboxMax[2]) / 2.0;

    double adx = std::abs(dx), ady = std::abs(dy), adz = std::abs(dz);
    if (adz > adx && adz > ady)
        return dz > 0 ? "above" : "below";
    if (adx > ady)
        return dx > 0 ? "east" : "west";
    return dy > 0 ? "north" : "south";
}

std::string CSceneGraph::InverseDirection(const std::string& dir)
{
    if (dir == "above") return "below";
    if (dir == "below") return "above";
    if (dir == "north") return "south";
    if (dir == "south") return "north";
    if (dir == "east") return "west";
    if (dir == "west") return "east";
    return dir;
}

std::string CSceneGraph::InverseRelationship(const std::string& rel)
{
    if (rel == "contains") return "within";
    if (rel == "supports") return "supported_by";
    if (rel == "above") return "below";
    return rel;
}

// ================================================================
// Edge Management
// ================================================================

void CSceneGraph::AddEdge(const SceneEdge& edge)
{
    m_edges.push_back(edge);
    m_edgesByNode[edge.sourceId].push_back(edge);
    m_edgesByNode[edge.targetId].push_back(edge);
}

void CSceneGraph::RemoveEdge(const std::string& srcId, const std::string& tgtId, const std::string& rel)
{
    // Shutdown preemption: this is an O(|m_edges|) full-vector scan called
    // in a per-edge loop from UpdateNodeFromEvent. On shutdown, any caller's
    // outer loop is already checking m_running — skipping the scan here
    // lets a modified node with many old edges abort mid-update.
    if (!m_running.load(std::memory_order_relaxed)) return;

    auto pred = [&](const SceneEdge& e) {
        return e.sourceId == srcId && e.targetId == tgtId && e.relationship == rel;
    };

    m_edges.erase(std::remove_if(m_edges.begin(), m_edges.end(), pred), m_edges.end());

    auto srcIt = m_edgesByNode.find(srcId);
    if (srcIt != m_edgesByNode.end())
        srcIt->second.erase(std::remove_if(srcIt->second.begin(), srcIt->second.end(), pred), srcIt->second.end());

    auto tgtIt = m_edgesByNode.find(tgtId);
    if (tgtIt != m_edgesByNode.end())
        tgtIt->second.erase(std::remove_if(tgtIt->second.begin(), tgtIt->second.end(), pred), tgtIt->second.end());
}

bool CSceneGraph::HasEdge(const std::string& idA, const std::string& idB) const
{
    auto it = m_edgesByNode.find(idA);
    if (it == m_edgesByNode.end()) return false;
    for (const auto& e : it->second)
    {
        if ((e.sourceId == idA && e.targetId == idB) ||
            (e.sourceId == idB && e.targetId == idA))
            return true;
    }
    return false;
}

// ================================================================
// Snapshot Publishing
// ================================================================

void CSceneGraph::PublishSnapshot()
{
    // Shutdown preemption: the snapshot deep-copies m_nodes + m_edges +
    // m_edgesByNode, which is multi-GB of allocation on a large graph.
    // No HTTP reader will consume a new snapshot after shutdown begins
    // (CRookServer has already been stopped), so skipping the publish is
    // safe and dramatically reduces observed unload latency on big files.
    if (!m_running.load(std::memory_order_relaxed)) return;

    auto snap = std::make_shared<SceneGraphSnapshot>();
    snap->nodes = m_nodes;  // deep copy (value semantics)
    snap->edges = m_edges;
    // Read m_sequence under m_diffMutex to stay consistent with GetDiff readers
    {
        std::lock_guard<std::mutex> lock(m_diffMutex);
        snap->sequence = m_sequence;
    }
    snap->profileName = m_activeProfile.name;

    // Copy edge index
    for (const auto& [id, edges] : m_edgesByNode)
        snap->edgesByNode[id] = edges;

    // Classification counts
    for (const auto& [id, node] : m_nodes)
    {
        std::string label = node.domainLabel.empty() ? node.shapeClass : node.domainLabel;
        if (label.empty()) label = "unclassified";
        snap->classificationCounts[label]++;
    }

    // Relationship counts
    for (const auto& edge : m_edges)
        snap->relationshipCounts[edge.relationship]++;

    // Atomic publish
    {
        std::lock_guard<std::mutex> lock(m_snapshotMutex);
        m_readSnapshot = std::move(snap);
    }
}

// ================================================================
// Diff Tracking
// ================================================================

void CSceneGraph::TrackChange(
    const SceneNode* added, const SceneNode* modified,
    const std::string* removedId,
    const std::vector<SceneEdge>* addedEdges,
    const std::vector<SceneEdge>* removedEdges)
{
    std::lock_guard<std::mutex> lock(m_diffMutex);
    m_sequence++;
    int seq = m_sequence;

    if (added)
        m_addedBySeq[seq].push_back(*added);
    if (modified)
        m_modifiedBySeq[seq].push_back(*modified);
    if (removedId)
        m_removedBySeq[seq].push_back(*removedId);
    if (addedEdges && !addedEdges->empty())
        m_addedEdgesBySeq[seq].insert(m_addedEdgesBySeq[seq].end(), addedEdges->begin(), addedEdges->end());
    if (removedEdges && !removedEdges->empty())
        m_removedEdgesBySeq[seq].insert(m_removedEdgesBySeq[seq].end(), removedEdges->begin(), removedEdges->end());

    PruneDiffHistory();
}

void CSceneGraph::PruneDiffHistory()
{
    const int maxHistory = 500;
    if (m_sequence <= maxHistory) return;

    int pruneBelow = m_sequence - maxHistory;
    auto pruneMap = [pruneBelow](auto& map) {
        for (auto it = map.begin(); it != map.end(); )
        {
            if (it->first < pruneBelow)
                it = map.erase(it);
            else
                ++it;
        }
    };

    pruneMap(m_addedBySeq);
    pruneMap(m_removedBySeq);
    pruneMap(m_modifiedBySeq);
    pruneMap(m_addedEdgesBySeq);
    pruneMap(m_removedEdgesBySeq);
}

// ================================================================
// Built-in Domain Profiles
// ================================================================

DomainProfile CSceneGraph::BuildGeneralProfile()
{
    DomainProfile p;
    p.name = "general";
    p.rules = {
        { "panel",     "vertical-planar",  {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "slab",      "horizontal-slab",  {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "bar",       "thin-horizontal",        {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "block",     "compact",          {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "post",      "thin-vertical",    {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "beam-like", "thin-horizontal",  {}, {}, {}, {}, {}, {}, {}, {}, 10 },
    };
    return p;
}

DomainProfile CSceneGraph::BuildArchitectureProfile()
{
    DomainProfile p;
    p.name = "architecture";
    p.rules = {
        // Architecture-specific (higher priority)
        { "wall",   "vertical-planar",  {}, {}, {}, {}, 0.15, {}, true,  {}, 20 },
        { "floor",  "horizontal-slab",  {}, {}, {}, {}, 0.1,  {}, {},    true, 20 },
        { "column", "thin-vertical",    3.0, {}, {}, {}, {},   {}, {},    {}, 20 },
        { "beam",   "thin-horizontal",  2.5, {}, {}, {}, {},   {}, {},    {}, 20 },
        // Fallback to general labels (lower priority)
        { "panel",     "vertical-planar",  {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "slab",      "horizontal-slab",  {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "bar",       "thin-horizontal",        {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "block",     "compact",          {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "post",      "thin-vertical",    {}, {}, {}, {}, {}, {}, {}, {}, 10 },
        { "beam-like", "thin-horizontal",  {}, {}, {}, {}, {}, {}, {}, {}, 10 },
    };
    return p;
}

// ================================================================
// Conduit Management
// ================================================================

CSceneGraphConduit* CSceneGraph::GetOrCreateConduit()
{
    // Must be called on the main thread (inside a Dispatch lambda).
    // Creates the conduit on first call; subsequent calls return the same instance.
    // Explicit teardown in Stop() ensures destructor runs before Rhino SDK teardown.
    if (!m_conduit)
        m_conduit = std::make_unique<CSceneGraphConduit>();
    return m_conduit.get();
}

} // namespace Rook
