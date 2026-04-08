// SceneGraphModels.h
//
// Plain-data structs for the scene graph system.
// No Rhino SDK pointers — safe to pass across thread boundaries.
// Mirrors C# SceneGraphModels.cs + ObjectEvent/ReconcileData.

#pragma once

#include <string>
#include <vector>
#include <array>
#include <unordered_map>
#include <optional>
#include <memory>

// ShapeMetrics struct and utilities — shared with BlocksHandler and others.
#include "Infrastructure/ShapeMetrics.h"

namespace Rook {

// ─── Scene Node ────────────────────────────────────────────────
// Represents a single Rhino object in the scene graph.

struct SceneNode {
    // Identity
    std::string id;
    std::string name;
    std::string layer;
    std::string geometryType;

    // Bounding box (axis-aligned)
    std::array<double, 3> bboxMin{};
    std::array<double, 3> bboxMax{};

    // Universal metrics
    ShapeMetrics metrics;

    // Classification
    std::string shapeClass;
    std::string domainLabel;
    double classConfidence = 0;

    // Provenance
    std::string createdBy;
    std::string creationIntent;
    std::string creationCommand;
    int sessionSequence = 0;
};

// ─── Scene Edge ────────────────────────────────────────────────
// Directed spatial relationship between two nodes.

struct SceneEdge {
    std::string sourceId;
    std::string targetId;
    std::string relationship;  // "contains","supports","adjacent","near","intersects","above"
    double distance = 0;
    double overlap = 0;
    std::string direction;     // "above","below","north","south","east","west"
};

// ─── Classification Rules ──────────────────────────────────────

struct ClassificationRule {
    std::string label;
    std::string shapeClass;
    std::optional<double> minElongation, maxElongation;
    std::optional<double> minFlatness, maxFlatness;
    std::optional<double> maxThinness;
    std::optional<double> minHeight;
    std::optional<bool> mustBeVertical;
    std::optional<bool> mustBeHorizontal;
    int priority = 0;
};

struct DomainProfile {
    std::string name = "general";
    std::vector<ClassificationRule> rules;
};

// ─── Immutable Snapshot ────────────────────────────────────────
// Published atomically by the background thread.
// Readers grab a shared_ptr<const SceneGraphSnapshot> — never lock.

struct SceneGraphSnapshot {
    std::unordered_map<std::string, SceneNode> nodes;
    std::vector<SceneEdge> edges;
    std::unordered_map<std::string, std::vector<SceneEdge>> edgesByNode;
    int sequence = 0;
    std::unordered_map<std::string, int> classificationCounts;
    std::unordered_map<std::string, int> relationshipCounts;
    std::string profileName = "general";
};

// ─── Diff ──────────────────────────────────────────────────────
// Change record for incremental sync (since a given sequence number).

struct SceneGraphDiff {
    int currentSequence = 0;
    bool truncated = false;  // True when sinceSequence is older than available history
    std::vector<SceneNode> addedNodes;
    std::vector<std::string> removedNodeIds;
    std::vector<SceneNode> modifiedNodes;
    std::vector<SceneEdge> addedEdges;
    std::vector<SceneEdge> removedEdges;
};

// ─── Lightweight event data captured on main thread ────────────
// CRhinoEventWatcher callbacks enqueue these to the background thread.

struct ObjectEvent {
    enum class Type { Created, Modified, Deleted };
    Type type = Type::Created;
    std::string id;          // UUID string
    std::string name;
    std::string layerPath;
    std::string geometryType;
    std::array<double, 3> bboxMin{};
    std::array<double, 3> bboxMax{};
    bool bboxValid = false;
    double unitScale = 1.0;
};

// ─── Reconcile data (full scene snapshot from main thread) ─────

struct ReconcileData {
    std::vector<ObjectEvent> liveObjects;
    double unitScale = 1.0;
};

} // namespace Rook
