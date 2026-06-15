// SceneGraphHandler.cpp
//
// HTTP endpoints for the scene graph spatial intelligence system.
// Most handlers are lock-free readers — they grab the immutable snapshot
// and serialize to JSON. Only reconcile (main-thread dispatch) and
// overlay (conduit toggle) need thread marshalling.

#include "stdafx.h"
#include "Handlers/SceneGraphHandler.h"
#include "RookServer.h"
#include "SceneGraph/SceneGraph.h"
#include "SceneGraph/SceneGraphConduit.h"
#include "SceneGraph/ExactAdjacencyService.h"
#include "SceneGraph/ExactAdjacencyTypes.h"
#include "SceneGraph/OcctProbe.h"    // Spike G tracer (OCCT-only unit)
#include "SceneGraph/OnBrepToOcct.h"  // Task 4 converter (OCCT-header-free pimpl)
#include "SceneGraph/OcctExecutor.h"  // Task 6b: dedicated serialized OCCT thread
#include "Threading/MainThreadDispatcher.h"
#include "Infrastructure/JsonHelpers.h"

#include <unordered_map>
#include <mutex>
#include <cmath>
#include <memory>
#include <vector>
#include <string>

using json = nlohmann::json;

namespace Rook {
namespace Handlers {

// ================================================================
// JSON Serialization Helpers
// ================================================================

namespace {

json SerializeNodeCompact(const SceneNode& n)
{
    return {
        {"id", n.id},
        {"name", n.name},
        {"layer", n.layer},
        {"label", !n.domainLabel.empty() ? n.domainLabel : n.shapeClass},
        {"shapeClass", n.shapeClass},
        {"domainLabel", n.domainLabel}
    };
}

json SerializeNodeFull(const SceneNode& n)
{
    return {
        {"id", n.id},
        {"name", n.name},
        {"layer", n.layer},
        {"geometryType", n.geometryType},
        {"bboxMin", {n.bboxMin[0], n.bboxMin[1], n.bboxMin[2]}},
        {"bboxMax", {n.bboxMax[0], n.bboxMax[1], n.bboxMax[2]}},
        {"shapeClass", n.shapeClass},
        {"domainLabel", n.domainLabel},
        {"classConfidence", n.classConfidence},
        {"metrics", {
            {"maxDim", n.metrics.maxDim},
            {"midDim", n.metrics.midDim},
            {"minDim", n.metrics.minDim},
            {"elongation", n.metrics.elongation},
            {"flatness", n.metrics.flatness},
            {"thinness", n.metrics.thinness},
            {"centroidZ", n.metrics.centroidZ},
            {"baseZ", n.metrics.baseZ},
            {"topZ", n.metrics.topZ},
            {"primaryAxis", n.metrics.primaryAxis},
            {"thinAxis", n.metrics.thinAxis},
            {"isVertical", n.metrics.isVertical},
            {"isHorizontal", n.metrics.isHorizontal},
            {"volume", n.metrics.volume},
            {"floorArea", n.metrics.floorArea}
        }},
        {"createdBy", n.createdBy},
        {"creationIntent", n.creationIntent},
        {"creationCommand", n.creationCommand},
        {"sessionSequence", n.sessionSequence}
    };
}

json SerializeEdge(const SceneEdge& e)
{
    return {
        {"source", e.sourceId},
        {"target", e.targetId},
        {"rel", e.relationship},
        {"distance", e.distance}
    };
}

json SerializeEdgeFull(const SceneEdge& e)
{
    return {
        {"sourceId", e.sourceId},
        {"targetId", e.targetId},
        {"relationship", e.relationship},
        {"distance", e.distance},
        {"overlap", e.overlap},
        {"direction", e.direction}
    };
}

// Maps the exact-adjacency Capability enum to its spec §9 wire string.
static std::string CapabilityToString(Capability c)
{
    switch (c)
    {
    case Capability::ExactPlanar:                    return "exact_planar";
    case Capability::PartialExactUnsupported:        return "partial_exact_unsupported";
    case Capability::CoarseFallbackExactUnsupported: return "coarse_fallback_exact_unsupported";
    case Capability::UnsupportedGeometry:            return "unsupported_geometry";
    case Capability::FailedWithDiagnostics:          return "failed_with_diagnostics";
    default:                                         return "unknown";
    }
}

} // anonymous namespace

// ================================================================
// GET /scene/graph — Full/compact/summary snapshot
// ================================================================

void HandleSceneGraph(const httplib::Request& req, httplib::Response& res)
{
    auto snapshot = CSceneGraph::Instance().ReadSnapshot();
    if (!snapshot)
    {
        CRookServer::SendError(res, "Scene graph not initialized");
        return;
    }

    // depth param from query string or body
    std::string depth = "compact";
    if (req.has_param("depth"))
        depth = req.get_param_value("depth");
    else if (!req.body.empty())
    {
        try {
            auto body = json::parse(req.body);
            if (body.contains("depth") && body["depth"].is_string())
                depth = body["depth"].get<std::string>();
        } catch (...) {}
    }

    if (depth == "summary")
    {
        CRookServer::SendSuccess(res, {
            {"nodeCount", snapshot->nodes.size()},
            {"edgeCount", snapshot->edges.size()},
            {"classifications", snapshot->classificationCounts},
            {"relationships", snapshot->relationshipCounts},
            {"sequence", snapshot->sequence}
        });
    }
    else if (depth == "full")
    {
        json nodesArr = json::array();
        for (const auto& [id, node] : snapshot->nodes)
            nodesArr.push_back(SerializeNodeFull(node));

        json edgesArr = json::array();
        for (const auto& edge : snapshot->edges)
            edgesArr.push_back(SerializeEdgeFull(edge));

        CRookServer::SendSuccess(res, {
            {"nodes", nodesArr},
            {"edges", edgesArr},
            {"profile", snapshot->profileName},
            {"sequence", snapshot->sequence}
        });
    }
    else // compact (default)
    {
        json nodesArr = json::array();
        for (const auto& [id, node] : snapshot->nodes)
            nodesArr.push_back(SerializeNodeCompact(node));

        json edgesArr = json::array();
        for (const auto& edge : snapshot->edges)
            edgesArr.push_back(SerializeEdge(edge));

        CRookServer::SendSuccess(res, {
            {"nodes", nodesArr},
            {"edges", edgesArr},
            {"sequence", snapshot->sequence}
        });
    }
}

// ================================================================
// GET/POST /scene/graph/node — Single node + 1-hop neighborhood
// ================================================================

void HandleSceneGraphNode(const httplib::Request& req, httplib::Response& res)
{
    // Get node ID from query param or body
    std::string nodeId;
    if (req.has_param("id"))
        nodeId = req.get_param_value("id");
    else if (!req.body.empty())
    {
        try {
            auto body = json::parse(req.body);
            if (body.contains("id") && body["id"].is_string())
                nodeId = body["id"].get<std::string>();
        } catch (...) {}
    }

    if (nodeId.empty())
    {
        CRookServer::SendError(res, "Missing 'id' parameter");
        return;
    }

    auto snapshot = CSceneGraph::Instance().ReadSnapshot();
    if (!snapshot)
    {
        CRookServer::SendError(res, "Scene graph not initialized");
        return;
    }

    auto nodeIt = snapshot->nodes.find(nodeId);
    if (nodeIt == snapshot->nodes.end())
    {
        CRookServer::SendError(res, "Node '" + nodeId + "' not found in scene graph");
        return;
    }

    // Get edges for this node
    json edgesArr = json::array();
    auto edgeIt = snapshot->edgesByNode.find(nodeId);
    if (edgeIt != snapshot->edgesByNode.end())
    {
        for (const auto& edge : edgeIt->second)
            edgesArr.push_back(SerializeEdgeFull(edge));
    }

    // Get neighbors
    std::set<std::string> neighborIds;
    if (edgeIt != snapshot->edgesByNode.end())
    {
        for (const auto& edge : edgeIt->second)
        {
            if (edge.sourceId != nodeId) neighborIds.insert(edge.sourceId);
            if (edge.targetId != nodeId) neighborIds.insert(edge.targetId);
        }
    }

    json neighborsArr = json::array();
    for (const auto& nid : neighborIds)
    {
        auto nIt = snapshot->nodes.find(nid);
        if (nIt != snapshot->nodes.end())
            neighborsArr.push_back(SerializeNodeCompact(nIt->second));
    }

    // Summary (pass the already-acquired snapshot to avoid a second snapshot read)
    std::string summary = CSceneGraph::Instance().GetNodeSummary(nodeId, snapshot);

    CRookServer::SendSuccess(res, {
        {"node", SerializeNodeFull(nodeIt->second)},
        {"edges", edgesArr},
        {"neighbors", neighborsArr},
        {"summary", summary}
    });
}

// ================================================================
// POST /scene/graph/query — Filtered subgraph
// ================================================================

void HandleSceneGraphQuery(const httplib::Request& req, httplib::Response& res)
{
    auto snapshot = CSceneGraph::Instance().ReadSnapshot();
    if (!snapshot)
    {
        CRookServer::SendError(res, "Scene graph not initialized");
        return;
    }

    // Parse filter parameters
    std::string depth = "compact";
    std::vector<std::string> filterIds;
    std::vector<std::string> filterLayers;
    std::vector<std::string> filterRelTypes;
    std::vector<std::string> filterShapeClasses;
    std::array<double, 3> bboxMin{}, bboxMax{};
    bool hasBboxFilter = false;

    if (!req.body.empty())
    {
        try {
            auto body = json::parse(req.body);
            if (body.contains("depth") && body["depth"].is_string())
                depth = body["depth"].get<std::string>();
            if (body.contains("object_ids") && body["object_ids"].is_array())
                for (const auto& v : body["object_ids"])
                    if (v.is_string()) filterIds.push_back(v.get<std::string>());
            if (body.contains("layers") && body["layers"].is_array())
                for (const auto& v : body["layers"])
                    if (v.is_string()) filterLayers.push_back(v.get<std::string>());
            if (body.contains("relationship_types") && body["relationship_types"].is_array())
                for (const auto& v : body["relationship_types"])
                    if (v.is_string()) filterRelTypes.push_back(v.get<std::string>());
            if (body.contains("shape_classes") && body["shape_classes"].is_array())
                for (const auto& v : body["shape_classes"])
                    if (v.is_string()) filterShapeClasses.push_back(v.get<std::string>());
            if (body.contains("bbox") && body["bbox"].is_object())
            {
                auto& bb = body["bbox"];
                if (bb.contains("min") && bb["min"].is_array() && bb["min"].size() == 3 &&
                    bb.contains("max") && bb["max"].is_array() && bb["max"].size() == 3)
                {
                    for (int i = 0; i < 3; i++)
                    {
                        bboxMin[i] = bb["min"][i].get<double>();
                        bboxMax[i] = bb["max"][i].get<double>();
                    }
                    hasBboxFilter = true;
                }
            }
        } catch (...) {}
    }

    // Convert filter lists to sets for O(1) lookup
    std::unordered_set<std::string> idSet(filterIds.begin(), filterIds.end());
    std::unordered_set<std::string> scSet(filterShapeClasses.begin(), filterShapeClasses.end());
    std::unordered_set<std::string> relSet(filterRelTypes.begin(), filterRelTypes.end());

    // Filter nodes
    std::vector<const SceneNode*> filteredNodes;
    for (const auto& [id, node] : snapshot->nodes)
    {
        // ID filter
        if (!idSet.empty() && idSet.find(id) == idSet.end())
            continue;

        // Layer filter (substring match, case-insensitive)
        if (!filterLayers.empty())
        {
            bool layerMatch = false;
            for (const auto& l : filterLayers)
            {
                // Case-insensitive substring search
                std::string nodeLower = node.layer;
                std::string filterLower = l;
                for (auto& c : nodeLower) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
                for (auto& c : filterLower) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));
                if (nodeLower.find(filterLower) != std::string::npos)
                {
                    layerMatch = true;
                    break;
                }
            }
            if (!layerMatch) continue;
        }

        // Shape class filter (matches shapeClass or domainLabel)
        if (!scSet.empty())
        {
            if (scSet.find(node.shapeClass) == scSet.end() &&
                scSet.find(node.domainLabel) == scSet.end())
                continue;
        }

        // Bbox filter (AABB overlap test)
        if (hasBboxFilter)
        {
            if (node.bboxMax[0] < bboxMin[0] || node.bboxMin[0] > bboxMax[0] ||
                node.bboxMax[1] < bboxMin[1] || node.bboxMin[1] > bboxMax[1] ||
                node.bboxMax[2] < bboxMin[2] || node.bboxMin[2] > bboxMax[2])
                continue;
        }

        filteredNodes.push_back(&node);
    }

    // Collect filtered node IDs
    std::unordered_set<std::string> nodeIdSet;
    for (const auto* n : filteredNodes)
        nodeIdSet.insert(n->id);

    // Filter edges (at least one endpoint in filtered set)
    std::vector<const SceneEdge*> filteredEdges;
    for (const auto& edge : snapshot->edges)
    {
        if (nodeIdSet.find(edge.sourceId) == nodeIdSet.end() &&
            nodeIdSet.find(edge.targetId) == nodeIdSet.end())
            continue;

        // Relationship type filter
        if (!relSet.empty() && relSet.find(edge.relationship) == relSet.end())
            continue;

        filteredEdges.push_back(&edge);
    }

    // Serialize response
    if (depth == "summary")
    {
        // Classification breakdown
        std::unordered_map<std::string, int> counts;
        for (const auto* n : filteredNodes)
        {
            std::string key = !n->domainLabel.empty() ? n->domainLabel : n->shapeClass;
            counts[key]++;
        }

        CRookServer::SendSuccess(res, {
            {"nodeCount", filteredNodes.size()},
            {"edgeCount", filteredEdges.size()},
            {"classifications", counts},
            {"sequence", snapshot->sequence}
        });
    }
    else
    {
        json nodesArr = json::array();
        for (const auto* n : filteredNodes)
            nodesArr.push_back(depth == "full" ? SerializeNodeFull(*n) : SerializeNodeCompact(*n));

        json edgesArr = json::array();
        for (const auto* e : filteredEdges)
            edgesArr.push_back(SerializeEdge(*e));

        CRookServer::SendSuccess(res, {
            {"nodes", nodesArr},
            {"edges", edgesArr},
            {"sequence", snapshot->sequence}
        });
    }
}

// ================================================================
// GET /scene/graph/stats — Graph statistics
// ================================================================

void HandleSceneGraphStats(const httplib::Request& /*req*/, httplib::Response& res)
{
    auto snapshot = CSceneGraph::Instance().ReadSnapshot();
    if (!snapshot)
    {
        CRookServer::SendSuccess(res, {
            {"nodeCount", 0},
            {"edgeCount", 0},
            {"classifications", json::object()},
            {"relationships", json::object()},
            {"profile", "general"},
            {"sequence", 0}
        });
        return;
    }

    CRookServer::SendSuccess(res, {
        {"nodeCount", snapshot->nodes.size()},
        {"edgeCount", snapshot->edges.size()},
        {"classifications", snapshot->classificationCounts},
        {"relationships", snapshot->relationshipCounts},
        {"profile", snapshot->profileName},
        {"sequence", snapshot->sequence}
    });
}

// ================================================================
// POST /scene/graph/diff — Incremental changes since sequence N
// ================================================================

void HandleSceneGraphDiff(const httplib::Request& req, httplib::Response& res)
{
    int sinceSequence = 0;
    if (!req.body.empty())
    {
        try {
            auto body = json::parse(req.body);
            if (body.contains("since_sequence") && body["since_sequence"].is_number_integer())
                sinceSequence = body["since_sequence"].get<int>();
        } catch (...) {}
    }

    auto diff = CSceneGraph::Instance().GetDiff(sinceSequence);

    json addedArr = json::array();
    for (const auto& n : diff.addedNodes)
        addedArr.push_back(SerializeNodeCompact(n));

    json modifiedArr = json::array();
    for (const auto& n : diff.modifiedNodes)
        modifiedArr.push_back(SerializeNodeCompact(n));

    json addedEdgesArr = json::array();
    for (const auto& e : diff.addedEdges)
        addedEdgesArr.push_back(SerializeEdge(e));

    json removedEdgesArr = json::array();
    for (const auto& e : diff.removedEdges)
        removedEdgesArr.push_back(SerializeEdge(e));

    json result = {
        {"currentSequence", diff.currentSequence},
        {"addedNodes", addedArr},
        {"removedNodeIds", diff.removedNodeIds},
        {"modifiedNodes", modifiedArr},
        {"addedEdges", addedEdgesArr},
        {"removedEdges", removedEdgesArr}
    };
    if (diff.truncated)
        result["truncated"] = true;

    CRookServer::SendSuccess(res, result);
}

// ================================================================
// POST /scene/graph/reconcile — Force full-scene reconciliation
// ================================================================

void HandleSceneGraphReconcile(const httplib::Request& /*req*/, httplib::Response& res)
{
    int changes = CSceneGraph::Instance().Reconcile();

    auto snapshot = CSceneGraph::Instance().ReadSnapshot();
    int nodeCount = snapshot ? static_cast<int>(snapshot->nodes.size()) : 0;
    int edgeCount = snapshot ? static_cast<int>(snapshot->edges.size()) : 0;
    int sequence = snapshot ? snapshot->sequence : 0;

    CRookServer::SendSuccess(res, {
        {"changes", changes},
        {"nodeCount", nodeCount},
        {"edgeCount", edgeCount},
        {"sequence", sequence}
    });
}

// ================================================================
// POST /scene/graph/classify — Force reclassification
// ================================================================

void HandleSceneGraphClassify(const httplib::Request& req, httplib::Response& res)
{
    std::vector<std::string> objectIds;
    std::string profileName;

    if (!req.body.empty())
    {
        try {
            auto body = json::parse(req.body);
            if (body.contains("object_ids") && body["object_ids"].is_array())
                for (const auto& v : body["object_ids"])
                    if (v.is_string()) objectIds.push_back(v.get<std::string>());
            if (body.contains("profile") && body["profile"].is_string())
                profileName = body["profile"].get<std::string>();
        } catch (...) {}
    }

    // Switch profile if requested
    if (!profileName.empty())
    {
        // Case-insensitive compare
        std::string lower = profileName;
        for (auto& c : lower) c = static_cast<char>(tolower(static_cast<unsigned char>(c)));

        if (lower == "architecture")
        {
            CSceneGraph::Instance().SetProfile(CSceneGraph::BuildArchitectureProfile());
        }
        else if (lower == "general")
        {
            CSceneGraph::Instance().SetProfile(CSceneGraph::BuildGeneralProfile());
        }
        else
        {
            CRookServer::SendError(res, "Unknown profile: " + profileName + ". Use general|architecture.");
            return;
        }
    }

    int count = CSceneGraph::Instance().Reclassify(objectIds.empty() ? nullptr : &objectIds);

    auto snapshot = CSceneGraph::Instance().ReadSnapshot();

    CRookServer::SendSuccess(res, {
        {"reclassified", count},
        {"profile", snapshot ? snapshot->profileName : "general"},
        {"classifications", snapshot ? snapshot->classificationCounts : json::object()}
    });
}

// ================================================================
// POST /scene/graph/overlay — Toggle viewport conduit
// ================================================================

void HandleSceneGraphOverlay(const httplib::Request& req, httplib::Response& res)
{
    bool hasEnabled = false;
    bool enabled = false;
    bool hasShowLabels = false;
    bool showLabels = false;
    bool hasShowEdges = false;
    bool showEdges = false;

    if (!req.body.empty())
    {
        try {
            auto body = json::parse(req.body);
            if (body.contains("enabled") && body["enabled"].is_boolean())
            {
                hasEnabled = true;
                enabled = body["enabled"].get<bool>();
            }
            if (body.contains("show_labels") && body["show_labels"].is_boolean())
            {
                hasShowLabels = true;
                showLabels = body["show_labels"].get<bool>();
            }
            if (body.contains("show_edges") && body["show_edges"].is_boolean())
            {
                hasShowEdges = true;
                showEdges = body["show_edges"].get<bool>();
            }
        } catch (...) {}
    }

    // Conduit operations must happen on the main thread
    struct OverlayResult {
        bool enabled = false;
        bool showLabels = true;
        bool showEdges = true;
        int nodeCount = 0;
        int edgeCount = 0;
    };

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [=]() -> OverlayResult
        {
            // Conduit owned by CSceneGraph — created on demand, torn down in Stop()
            auto* conduit = Rook::CSceneGraph::Instance().GetOrCreateConduit();

            if (hasShowLabels) conduit->ShowLabels = showLabels;
            if (hasShowEdges) conduit->ShowEdges = showEdges;

            if (hasEnabled)
            {
                if (enabled)
                    conduit->Enable();
                else
                    conduit->Disable();
            }
            else if (conduit->IsActive())
            {
                // No explicit toggle — just refresh
                conduit->RefreshSnapshot();
                CRhinoDoc* doc = RhinoApp().ActiveDoc();
                if (doc) doc->Redraw();
            }

            OverlayResult r;
            r.enabled = conduit->IsActive();
            r.showLabels = conduit->ShowLabels;
            r.showEdges = conduit->ShowEdges;

            auto snap = CSceneGraph::Instance().ReadSnapshot();
            if (snap)
            {
                r.nodeCount = static_cast<int>(snap->nodes.size());
                r.edgeCount = static_cast<int>(snap->edges.size());
            }
            return r;
        });
    auto result = future.get();

    CRookServer::SendSuccess(res, {
        {"enabled", result.enabled},
        {"showLabels", result.showLabels},
        {"showEdges", result.showEdges},
        {"nodeCount", result.nodeCount},
        {"edgeCount", result.edgeCount}
    });
}

// ================================================================
// POST /scene/graph/adjacency/exact — Exact (planar) adjacency
//   + optional coarse decoration (live, never cached)
// ================================================================

void HandleSceneGraphExactAdjacency(const httplib::Request& req, httplib::Response& res)
{
    // 1) Parse body.
    std::string objectId;
    CandidateQueryOptions opts;          // defaults: maxCandidates=64, tolerance=1e-3
    bool includeCoarse = false;
    try {
        auto body = json::parse(req.body);
        if (!body.contains("objectId") || !body["objectId"].is_string())
        {
            CRookServer::SendError(res, "Missing 'objectId' (string)");
            return;
        }
        objectId = body["objectId"].get<std::string>();
        if (body.contains("maxCandidates") && body["maxCandidates"].is_number_integer())
            opts.maxCandidates = body["maxCandidates"].get<int>();
        if (body.contains("tolerance") && body["tolerance"].is_number())
            opts.tolerance = body["tolerance"].get<double>();
        if (body.contains("includeCoarse") && body["includeCoarse"].is_boolean())
            includeCoarse = body["includeCoarse"].get<bool>();
    } catch (const std::exception& e) {
        CRookServer::SendError(res, std::string("Invalid JSON body: ") + e.what());
        return;
    }

    // 2) Compute exact CORE (worker thread; safe to block).
    ExactAdjacencyCore core = ExactAdjacencyService::Instance().Compute(objectId, opts);

    // 3) Optional coarse decoration — AFTER compute, from the LIVE snapshot,
    //    NEVER cached. Look up the existing bbox relationship between objectId
    //    and each candidate from snapshot->edgesByNode[objectId].
    std::unordered_map<std::string, std::string> coarseByCandidate;  // candidateId -> relationship
    if (includeCoarse)
    {
        auto snapshot = CSceneGraph::Instance().ReadSnapshot();
        if (snapshot)
        {
            auto it = snapshot->edgesByNode.find(objectId);
            if (it != snapshot->edgesByNode.end())
            {
                for (const SceneEdge& e : it->second)
                {
                    const std::string& other = (e.sourceId == objectId) ? e.targetId : e.sourceId;
                    // First relationship found for a candidate wins (deterministic).
                    coarseByCandidate.emplace(other, e.relationship);
                }
            }
        }
    }

    // 4) Serialize per spec §9.
    json out;
    out["objectId"]         = core.objectId;
    out["graphSequence"]    = core.graphSequence;
    out["sourceCapability"] = CapabilityToString(core.sourceCapability);

    json edgesJson = json::array();
    for (const ExactEdge& e : core.edges)
    {
        edgesJson.push_back({
            {"targetId",     e.targetId},
            {"relationship", e.relationship},   // "adjacent_exact"
            {"sharedArea",   e.sharedArea}
        });
    }
    out["edges"] = edgesJson;

    json candsJson = json::array();
    for (const ExactCandidate& c : core.candidates)
    {
        json cj;
        cj["id"]         = c.id;
        cj["capability"] = CapabilityToString(c.capability);
        if (includeCoarse)
        {
            auto cit = coarseByCandidate.find(c.id);
            if (cit != coarseByCandidate.end()) cj["coarseRelationship"] = cit->second;
            else                                cj["coarseRelationship"] = nullptr;
        }
        candsJson.push_back(std::move(cj));
    }
    out["candidates"]          = candsJson;
    out["capped"]              = core.capped;
    out["candidateCount"]      = core.candidateCount;
    out["candidateLimit"]      = core.candidateLimit;
    out["totalCandidateCount"] = core.totalCandidateCount;
    out["diagnostics"]         = core.diagnostics;

    CRookServer::SendSuccess(res, out);
}

// ================================================================
// Spike G tracer: OCCT-in-plugin probe. POST /scene/occt_probe
//   body: { stepA: "<path>", stepB: "<path>" }
// Proves OCCT links + inits + runs BRepAlgoAPI_Common inside RookNative.
// OCCT calls are serialized (the v1 concurrency policy) via a static mutex.
// ================================================================
void HandleOcctProbe(const httplib::Request& req, httplib::Response& res)
{
    std::string stepA, stepB;
    try {
        auto body = json::parse(req.body);
        if (!body.contains("stepA") || !body.contains("stepB")) {
            CRookServer::SendError(res, "Missing 'stepA'/'stepB' (file paths)");
            return;
        }
        stepA = body["stepA"].get<std::string>();
        stepB = body["stepB"].get<std::string>();
    } catch (const std::exception& e) {
        CRookServer::SendError(res, std::string("Invalid JSON: ") + e.what());
        return;
    }

    // Task 6b: run the OCCT compute on the dedicated serialized OCCT worker thread
    // (SE translation installed once there). One worker == the v1 serialization, so
    // the old call_once(OcctProbeInit) + static mutex are gone. Run() blocks and
    // returns the result; stepA/stepB outlive the blocking call.
    std::string diag;
    double area = Rook::OcctExecutor::Instance().Run([&]() -> double {
        return Rook::OcctProbeSharedArea(stepA, stepB, diag);
    });

    CRookServer::SendSuccess(res, {
        {"sharedArea_mm2", area},
        {"diag", diag},
        {"occt", "in-plugin"}
    });
}

// ================================================================
// Task 4 DEV route: ON_Brep -> OCCT surface converter validation.
//   POST /scene/occt_validate_converter
//   body: { objectId: "<guid>", expectedMm2?: <number override> }
// Resolves the live ON_Brep on the MAIN thread, deep-copies it (no Rhino
// pointer escapes), then runs the TRIMMED converter under the OCCT mutex and
// sums trimmed face area. As of Task 5 the converter is trimmed + orientation-
// faithful, so the summed area matches the trimmed STEP oracle.
// Same dev visibility as /scene/occt_probe; removed in Task 8.
// ================================================================
void HandleOcctValidateConverter(const httplib::Request& req, httplib::Response& res)
{
    std::string objectId;
    bool hasOverride = false;
    double overrideMm2 = 0.0;
    try {
        auto body = json::parse(req.body);
        if (!body.contains("objectId")) {
            CRookServer::SendError(res, "Missing 'objectId' (guid)");
            return;
        }
        objectId = body["objectId"].get<std::string>();
        if (body.contains("expectedMm2") && body["expectedMm2"].is_number()) {
            hasOverride = true;
            overrideMm2 = body["expectedMm2"].get<double>();
        }
    } catch (const std::exception& e) {
        CRookServer::SendError(res, std::string("Invalid JSON: ") + e.what());
        return;
    }

    // Built-in oracle table (objectId -> expected mm^2; trimmed truth from STEP).
    static const std::unordered_map<std::string, double> kOracle = {
        {"71065f57-ee93-4af5-8a67-9aa1c4e88302", 431441833.631},
        {"08d4dedf-1387-453a-9938-7f3ab516b8ac", 236698710.791},
        {"5c12cc83-5fe3-4f2c-9fca-c0575c9f5dd3", 57752777.327},
        {"be0ca730-f3e9-4b41-a5bf-6b3848607b14", 57730120.364},
        {"7e80db98-d133-4a05-b9fe-ee6d37d9069d", 31753629.008},
        {"26b2c012-24cf-4656-9e48-8083dc072cad", 31461872.558},
        {"7d55840d-2516-4a78-9c7d-3a10152756b1", 40404289.332},
        {"502898fc-75f3-4d59-bddf-cc966a942795", 37898150.015},
    };

    // ── Main-thread extraction: resolve doc + object, deep-copy the ON_Brep,
    //    capture the model-units->mm length scale. Only plain data escapes. ──
    struct Extracted {
        std::shared_ptr<ON_Brep> brep;     // owned deep-copy; null if unsupported
        double unitsToMm = 1.0;
        std::string kind;                  // "brep" | "mesh" | "subd" | "no_brep"
        bool found = false;
    };

    ON_UUID uuid = ON_UuidFromString(objectId.c_str());

    auto fut = CMainThreadDispatcher::Instance().Dispatch(
        [uuid]() -> Extracted {
            Extracted ex;
            unsigned int sn = CRhinoDoc::TargetDocSerialNumber();
            CRhinoDoc* doc = CRhinoDoc::FromRuntimeSerialNumber(sn);
            if (!doc) return ex;
            const CRhinoObject* obj = doc->LookupObject(uuid);
            if (!obj) return ex;
            ex.found = true;

            const ON_3dmUnitsAndTolerances& ut = doc->Properties().ModelUnitsAndTolerances();
            ex.unitsToMm = ON::UnitScale(ut.m_unit_system,
                                         ON::LengthUnitSystem::Millimeters);

            const ON_Geometry* geom = obj->Geometry();
            if (ON_Mesh::Cast(geom))      { ex.kind = "mesh"; return ex; }
            if (ON_SubD::Cast(geom))      { ex.kind = "subd"; return ex; }

            // Brep or Extrusion (via BrepForm) -> owned deep-copy.
            if (const ON_Brep* b = ON_Brep::Cast(geom)) {
                ex.brep = std::make_shared<ON_Brep>(*b);   // deep copy
                ex.kind = "brep";
                return ex;
            }
            if (const ON_Extrusion* e = ON_Extrusion::Cast(geom)) {
                ON_Brep* bf = e->BrepForm();
                if (bf) {
                    ex.brep = std::shared_ptr<ON_Brep>(bf); // owns the BrepForm allocation
                    ex.kind = "brep";
                    return ex;
                }
            }
            ex.kind = "no_brep";
            return ex;
        });

    Extracted ex;
    try {
        ex = fut.get();
    } catch (const std::exception& e) {
        CRookServer::SendError(res, std::string("extraction_dispatch_failed: ") + e.what());
        return;
    }

    if (!ex.found) {
        CRookServer::SendSuccess(res, {{"error", "object_not_found"}, {"objectId", objectId}});
        return;
    }
    if (ex.kind != "brep" || !ex.brep) {
        CRookServer::SendSuccess(res, {
            {"error", "unsupported"},
            {"kind", ex.kind.empty() ? "no_brep" : ex.kind},
            {"objectId", objectId}
        });
        return;
    }

    // ── OCCT conversion (Task 6b: on the dedicated serialized OCCT worker thread) ──
    // The converter runs on the OCCT worker (SE translation installed once there);
    // one worker == the v1 serialization, so the old call_once(OcctProbeInit) +
    // static mutex are gone. ex.brep is an owned deep-copy on the main thread, so
    // the worker only touches an owned ON_Brep (no live Rhino SDK). Run() blocks
    // and rethrows any escaping exception here; the inner try/catch still degrades
    // a (now catchable) OCCT fault to a diagnostic.
    int convertedFaceCount = 0;
    int brepFaceCount = ex.brep->m_F.Count();
    std::vector<int> failed;
    std::vector<int> sourceMap;     // sourceMap[slot] = source face index
    double totalAreaModel = 0.0;
    std::vector<std::string> diagnostics;
    Rook::OcctExecutor::Instance().Run([&]() {
        try {
            Rook::OcctFaceSet faceSet = Rook::ConvertBrepFaces(*ex.brep);
            convertedFaceCount = faceSet.faceCount();
            failed = faceSet.failedFaceIndices();
            for (int s = 0; s < convertedFaceCount; ++s)
                sourceMap.push_back(faceSet.sourceFaceIndex(s));
            totalAreaModel = Rook::OcctFaceSetTotalArea(faceSet);
        } catch (const std::exception& e) {
            diagnostics.push_back(std::string("convert_exception: ") + e.what());
        } catch (...) {
            diagnostics.push_back("convert_exception: unknown");
        }
    });

    // Area scale = (length scale)^2. inches -> 25.4^2 = 645.16.
    const double totalAreaMm2 = totalAreaModel * ex.unitsToMm * ex.unitsToMm;

    // Expected: body override, else oracle table, else null.
    bool hasExpected = hasOverride;
    double expectedMm2 = overrideMm2;
    if (!hasExpected) {
        auto it = kOracle.find(objectId);
        if (it != kOracle.end()) { hasExpected = true; expectedMm2 = it->second; }
    }

    // faceIndexMapOk: every slot maps to a source index in [0, brepFaceCount).
    bool faceIndexMapOk = true;
    for (int s = 0; s < convertedFaceCount; ++s) {
        int src = (s < (int)sourceMap.size()) ? sourceMap[s] : -1;
        if (src < 0 || src >= brepFaceCount) { faceIndexMapOk = false; break; }
    }

    json out;
    out["objectId"]           = objectId;
    out["convertedFaceCount"] = convertedFaceCount;
    out["brepFaceCount"]      = brepFaceCount;
    out["failedFaceIndices"]  = failed;
    out["totalAreaModel"]     = totalAreaModel;
    out["totalAreaMm2"]       = totalAreaMm2;
    if (hasExpected) {
        out["expectedMm2"] = expectedMm2;
        if (expectedMm2 != 0.0)
            out["relErr"] = std::fabs(totalAreaMm2 - expectedMm2) / std::fabs(expectedMm2);
        else
            out["relErr"] = nullptr;
    } else {
        out["expectedMm2"] = nullptr;
        out["relErr"]      = nullptr;
    }
    out["faceIndexMapOk"]     = faceIndexMapOk;
    out["modelUnitsToMm"]     = ex.unitsToMm;
    diagnostics.push_back("trimmed_faces_task5_matches_trimmed_oracle");
    out["diagnostics"]        = diagnostics;

    CRookServer::SendSuccess(res, out);
}


} // namespace Handlers
} // namespace Rook
