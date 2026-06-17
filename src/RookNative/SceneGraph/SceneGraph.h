// SceneGraph.h
//
// Core scene graph engine. Maintains a continuous shadow graph of Rhino objects
// with spatial relationships, classification, and incremental diff tracking.
//
// Architecture: Producer-consumer with immutable snapshots.
// - Main thread (CRhinoEventWatcher): captures lightweight ObjectEvents
// - Background thread: processes updates, builds RTree, computes relationships
// - Readers (HTTP handlers, conduit): read from immutable shared_ptr snapshot
//
// The C++ version improves on C# by using per-object CRhinoEventWatcher
// instead of full-scene scans after every command.

#pragma once

#include "SceneGraph/SceneGraphModels.h"
#include "SceneGraph/ExactAdjacencyTypes.h"
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <queue>
#include <functional>
#include <set>

class CSceneGraphWatcher;  // Forward — defined in SceneGraphWatcher.h
class ON_RTree;

namespace Rook {

class CSceneGraphConduit;  // Forward — defined in SceneGraphConduit.h

class CSceneGraph
{
public:
    CSceneGraph();
    ~CSceneGraph();

    // ─── Lifecycle ────────────────────────────────────────────
    void Start();     // Start background thread + register event watcher
    void Stop();      // Signal shutdown, join thread, unregister watcher

    static CSceneGraph& Instance();

    // ─── Event intake (called from CSceneGraphWatcher, main thread) ─
    void EnqueueEvent(ObjectEvent&& event);

    // ─── Action intake (called from HTTP handlers, worker threads) ──
    // Enqueues a callable to run on the background thread. Returns a future.
    template<typename F>
    auto EnqueueAction(F&& func) -> std::future<std::invoke_result_t<F>>;

    // ─── Read API (lock-free via shared_ptr<const SceneGraphSnapshot>) ─
    std::shared_ptr<const SceneGraphSnapshot> ReadSnapshot() const;
    int Sequence() const;
    int NodeCount() const;
    int EdgeCount() const;
    // ─── Conduit management (main thread only) ──────────────────
    CSceneGraphConduit* GetOrCreateConduit();

    // ─── Mutation API (blocks until background thread processes) ────
    int Reconcile();                // Full scene reconciliation via main-thread Dispatch
    void SetProfile(DomainProfile profile);
    int Reclassify(const std::vector<std::string>* objectIds = nullptr);
    void Clear();

    // ─── Async mutation (non-blocking, for main-thread callers) ──
    void ReconcileAsync(CRhinoDoc& doc);  // Fire-and-forget reconcile from watcher/startup
    void ClearAsync();                     // Fire-and-forget clear on document close

    // ─── Query API ──────────────────────────────────────────────
    SceneGraphDiff GetDiff(int sinceSequence) const;
    std::string GetNodeSummary(const std::string& objectId,
        std::shared_ptr<const SceneGraphSnapshot> snapshot = nullptr) const;

    // Lazy candidate query for exact-adjacency refinement. Runs on the processor
    // thread (RTree-safe). Returns a deterministic nearest-first, then capped, set.
    std::future<CandidateQueryResult>
    QueryCandidatesAsync(const std::string& objectId, const CandidateQueryOptions& opts);

    // ─── Built-in profiles ──────────────────────────────────────
    static DomainProfile BuildGeneralProfile();
    static DomainProfile BuildArchitectureProfile();

private:
    // ─── Background processor ────────────────────────────────
    void ProcessorLoop();
    void ProcessEvents(std::vector<ObjectEvent>& batch);
    int ProcessReconcile(const ReconcileData& data);

    // ─── Main-thread capture helper ─────────────────────────
    static ReconcileData CaptureReconcileData(CRhinoDoc& doc);

    // ─── Clear helper (background thread only) ──────────────
    void ClearInternal();  // Shared by Clear() and ClearAsync()

    // ─── Node operations (background thread only) ────────────
    SceneNode BuildNodeFromEvent(const ObjectEvent& ev);
    std::vector<SceneEdge> UpdateNodeFromEvent(const ObjectEvent& ev);

    // Batch node removal — O(|m_edges|) regardless of |ids|. Does a single
    // remove_if pass over m_edges with a set-membership predicate instead
    // of N passes, which is the algorithmic fix for the large-file close
    // hotspot identified in Rhino.DMP 2026-04-07.
    void RemoveNodesBulk(const std::vector<std::string>& ids);

    // ─── Classification ──────────────────────────────────────
    // ComputeMetrics and DetermineShapeClass are now free functions
    // in Infrastructure/ShapeMetrics.h (shared with BlocksHandler).
    void Classify(SceneNode& node);
    static bool MatchesRule(const ShapeMetrics& m, const ClassificationRule& rule);
    static double ComputeRuleConfidence(const ShapeMetrics& m, const ClassificationRule& rule);

    // ─── Spatial relationships ───────────────────────────────
    std::vector<SceneEdge> ComputeRelationships(const SceneNode& node);
    std::vector<SceneEdge> ComputePairRelationships(
        const SceneNode& a, const SceneNode& b, double unitScale);
    std::vector<std::string> FindNeighborIds(const SceneNode& node);
    void RebuildRTree();

    // ─── Edge management ─────────────────────────────────────
    void AddEdge(const SceneEdge& edge);
    void RemoveEdge(const std::string& srcId, const std::string& tgtId, const std::string& rel);
    bool HasEdge(const std::string& idA, const std::string& idB) const;

    // ─── Geometry helpers ────────────────────────────────────
    static double BBoxDistance(const std::array<double,3>& aMin, const std::array<double,3>& aMax,
                               const std::array<double,3>& bMin, const std::array<double,3>& bMax);
    static double BBoxOverlapVolume(const std::array<double,3>& aMin, const std::array<double,3>& aMax,
                                     const std::array<double,3>& bMin, const std::array<double,3>& bMax);
    static bool BBoxContains(const std::array<double,3>& outerMin, const std::array<double,3>& outerMax,
                              const std::array<double,3>& innerMin, const std::array<double,3>& innerMax);
    static double HorizontalOverlapFraction(
        const std::array<double,3>& aMin, const std::array<double,3>& aMax,
        const std::array<double,3>& bMin, const std::array<double,3>& bMax);
    static std::string ComputeDirection(const SceneNode& a, const SceneNode& b);
    static std::string InverseDirection(const std::string& dir);
    static std::string InverseRelationship(const std::string& rel);

    // ─── Snapshot publishing ─────────────────────────────────
    void PublishSnapshot();

    // ─── Diff tracking ───────────────────────────────────────
    void TrackChange(const SceneNode* added, const SceneNode* modified,
                     const std::string* removedId,
                     const std::vector<SceneEdge>* addedEdges,
                     const std::vector<SceneEdge>* removedEdges);
    void PruneDiffHistory();

    // ─── Writer state (background thread only) ───────────────
    std::unordered_map<std::string, SceneNode> m_nodes;
    std::vector<SceneEdge> m_edges;
    std::unordered_map<std::string, std::vector<SceneEdge>> m_edgesByNode;
    std::unique_ptr<ON_RTree> m_rtree;
    std::vector<std::string> m_rtreeIdOrder;
    DomainProfile m_activeProfile;
    double m_cachedUnitScale = 1.0;
    int m_sequence = 0;  // Protected by m_diffMutex (not atomic — all access is under mutex)
    double m_proximityThreshold = 2.0;  // meters equivalent

    // ─── Diff history (protected by m_diffMutex) ────────────
    mutable std::mutex m_diffMutex;
    std::unordered_map<int, std::vector<SceneNode>> m_addedBySeq;
    std::unordered_map<int, std::vector<std::string>> m_removedBySeq;
    std::unordered_map<int, std::vector<SceneNode>> m_modifiedBySeq;
    std::unordered_map<int, std::vector<SceneEdge>> m_addedEdgesBySeq;
    std::unordered_map<int, std::vector<SceneEdge>> m_removedEdgesBySeq;

    // ─── Event queue (mutex-protected, main thread → background) ─
    std::mutex m_eventMutex;
    std::vector<ObjectEvent> m_eventQueue;

    // ─── Action queue (mutex-protected, HTTP threads → background) ─
    std::mutex m_actionMutex;
    std::queue<std::function<void()>> m_actionQueue;

    // ─── Background thread sync ──────────────────────────────
    std::thread m_processorThread;
    std::condition_variable m_cv;
    std::mutex m_cvMutex;
    bool m_hasPendingWork = false;   // Protected by m_cvMutex
    std::atomic<bool> m_running{false};

    // ─── Immutable snapshot (C++17: mutex + shared_ptr) ──────
    mutable std::mutex m_snapshotMutex;
    std::shared_ptr<const SceneGraphSnapshot> m_readSnapshot;

    // ─── Display conduit (main-thread-only, created on demand) ─
    std::unique_ptr<CSceneGraphConduit> m_conduit;

    // ─── Event watcher (owned, registered with Rhino) ────────
    std::unique_ptr<CSceneGraphWatcher> m_watcher;
};

// ─── Template implementation ─────────────────────────────────

template<typename F>
auto CSceneGraph::EnqueueAction(F&& func) -> std::future<std::invoke_result_t<F>>
{
    using ReturnType = std::invoke_result_t<F>;
    auto task = std::make_shared<std::packaged_task<ReturnType()>>(std::forward<F>(func));
    auto future = task->get_future();

    {
        std::lock_guard<std::mutex> lock(m_actionMutex);
        m_actionQueue.push([task]() { (*task)(); });
    }
    {
        std::lock_guard<std::mutex> lock(m_cvMutex);
        m_hasPendingWork = true;
    }
    m_cv.notify_one();

    return future;
}

} // namespace Rook
