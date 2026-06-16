// OcctAdjacencyValidateHandler.cpp
//
// Task 6 DEV route: in-plugin OcctAdjacencyEngine::Evaluate validation.
//   POST /scene/occt_validate_adjacency
//   body: { sourceId: "<guid>", candidateIds: ["<guid>", ...], fuzzMm?: <number> }
//
// NAMESPACE-ISOLATED ON PURPOSE: the LEGACY ExactAdjacencyTypes.h defines structs with
// the SAME names (ExactEdge/ExactCandidate/ExactAdjacencyCore/Capability/FacePair) directly
// in namespace Rook, used by the production /scene/graph/adjacency/exact route in
// SceneGraphHandler.cpp. The Task-6 OCCT contract therefore lives in the DISTINCT nested
// namespace Rook::occt (OcctAdjacencyTypes.h) so the two definitions have different mangled
// names and CANNOT collide via ODR. (They did before: std::vector<Rook::ExactEdge> was
// instantiated against both layouts and the linker folded them to one under /GL, driving the
// engine's vector with the wrong element stride — the 2026-06-15 in-Rhino heisenbug.) This
// file uses Rook::occt exclusively and never includes the legacy header. The legacy contract
// is stripped in Task 8; until then the namespaces keep both routes safe.
//
// Resolves the source + each candidate ON_Brep on the MAIN thread, deep-copies
// each into an ObjectBrepPayload (mesh/SubD/non-Brep -> brep=nullptr + capability
// + diagnostic), captures the model-units->mm scale, computes
// tolModelUnits = fuzzMm / modelUnitsToMillimeters, then runs the engine, whose
// OCCT compute is serialized on the dedicated OCCT worker thread (Task 6b
// OcctExecutor; SE translation installed once there).

#include "stdafx.h"   // RhinoSdk -> opennurbs (ON_Brep) available; PCH like other handlers
#include "Handlers/SceneGraphHandler.h"     // declares HandleOcctValidateAdjacency
#include "RookServer.h"
#include "SceneGraph/OcctAdjacencyTypes.h"   // Task 6 contract (OCCT-header-free)
#include "SceneGraph/OcctAdjacencyEngine.h"  // Task 6 engine (OCCT-header-free pimpl)
#include "Threading/MainThreadDispatcher.h"
#include "Infrastructure/JsonHelpers.h"

#include <string>
#include <vector>

using json = nlohmann::json;

namespace Rook {
namespace Handlers {

// The OCCT exact-adjacency contract lives in Rook::occt (ODR-isolation from the legacy
// Rook::* contract — see OcctAdjacencyTypes.h). An explicit alias + per-use qualification
// (rather than `using namespace`) makes it impossible to accidentally bind a legacy
// Rook::* name and keeps the namespace boundary visible at every call site.
namespace ro = ::Rook::occt;

namespace {

// Main-thread extraction of ONE object into an ObjectBrepPayload. Returns the
// payload by value; brep is an owned deep-copy (null if unsupported / not found).
ro::ObjectBrepPayload ExtractPayload(const std::string& id,
                                     double& unitsToMmOut, bool& foundOut)
{
    ON_UUID uuid = ON_UuidFromString(id.c_str());
    struct Raw { ON_Brep* brep = nullptr; double unitsToMm = 1.0;
                 std::string kind; bool found = false; };
    auto fut = CMainThreadDispatcher::Instance().Dispatch(
        [uuid]() -> Raw {
            Raw r;
            unsigned int sn = CRhinoDoc::TargetDocSerialNumber();
            CRhinoDoc* doc = CRhinoDoc::FromRuntimeSerialNumber(sn);
            if (!doc) return r;
            const CRhinoObject* obj = doc->LookupObject(uuid);
            if (!obj) return r;
            r.found = true;
            const ON_3dmUnitsAndTolerances& ut =
                doc->Properties().ModelUnitsAndTolerances();
            r.unitsToMm = ON::UnitScale(ut.m_unit_system,
                                        ON::LengthUnitSystem::Millimeters);
            const ON_Geometry* geom = obj->Geometry();
            if (ON_Mesh::Cast(geom)) { r.kind = "mesh"; return r; }
            if (ON_SubD::Cast(geom)) { r.kind = "subd"; return r; }
            if (const ON_Brep* b = ON_Brep::Cast(geom)) {
                r.brep = new ON_Brep(*b);   // owned deep-copy
                r.kind = "brep";
                return r;
            }
            if (const ON_Extrusion* e = ON_Extrusion::Cast(geom)) {
                ON_Brep* bf = e->BrepForm();
                if (bf) { r.brep = bf; r.kind = "brep"; return r; }
            }
            r.kind = "no_brep";
            return r;
        });
    Raw raw;
    try { raw = fut.get(); }
    catch (...) { raw = Raw{}; }

    ro::ObjectBrepPayload p;
    p.objectId = id;
    unitsToMmOut = raw.unitsToMm;
    foundOut = raw.found;
    p.modelUnitsToMillimeters = raw.unitsToMm;
    if (!raw.found) {
        p.capability = ro::Capability::FailedWithDiagnostics;
        p.diagnostics.push_back("object_not_found");
        return p;
    }
    if (raw.kind == "brep" && raw.brep) {
        p.brep.reset(raw.brep);   // unique_ptr<const ON_Brep> takes ownership
        p.capability = ro::Capability::ExactBrep;   // refined by the engine on convert
    } else if (raw.kind == "mesh" || raw.kind == "subd") {
        p.capability = ro::Capability::UnsupportedGeometry;
        p.diagnostics.push_back(std::string("unsupported_") + raw.kind);
    } else {
        p.capability = ro::Capability::FailedWithDiagnostics;
        p.diagnostics.push_back("no_brep");
    }
    return p;
}

} // namespace

void HandleOcctValidateAdjacency(const httplib::Request& req, httplib::Response& res)
{
    std::string sourceId;
    std::vector<std::string> candidateIds;
    double fuzzMm = ro::kDefaultFuzzMm;
    try {
        auto body = json::parse(req.body);
        if (!body.contains("sourceId")) {
            CRookServer::SendError(res, "Missing 'sourceId' (guid)");
            return;
        }
        sourceId = body["sourceId"].get<std::string>();
        if (body.contains("candidateIds") && body["candidateIds"].is_array()) {
            for (const auto& c : body["candidateIds"])
                if (c.is_string()) candidateIds.push_back(c.get<std::string>());
        }
        if (body.contains("fuzzMm") && body["fuzzMm"].is_number())
            fuzzMm = body["fuzzMm"].get<double>();
    } catch (const std::exception& e) {
        CRookServer::SendError(res, std::string("Invalid JSON: ") + e.what());
        return;
    }

    double srcUnitsToMm = 1.0;
    bool srcFound = false;
    ro::ObjectBrepPayload source = ExtractPayload(sourceId, srcUnitsToMm, srcFound);
    if (!srcFound) {
        CRookServer::SendSuccess(res, {{"error", "source_not_found"}, {"sourceId", sourceId}});
        return;
    }

    std::vector<ro::ObjectBrepPayload> candidates;
    candidates.reserve(candidateIds.size());
    for (const std::string& cid : candidateIds) {
        double um = 1.0; bool found = false;
        candidates.push_back(ExtractPayload(cid, um, found));
    }

    // Tolerance in model units = fuzzMm / (model-units -> mm).
    const double tolModelUnits =
        (srcUnitsToMm != 0.0) ? (fuzzMm / srcUnitsToMm) : fuzzMm;

    // Task 6b: OcctProbeInit (OSD::SetSignal) is now installed ONCE on the
    // dedicated OCCT worker thread inside OcctExecutor; OcctAdjacencyEngine::Evaluate
    // routes its OCCT compute through that executor. No per-handler call_once /
    // mutex is needed — the engine call below is serialized + SE-translated there.
    ro::ExactAdjacencyCore core;
    try {
        core = ro::OcctAdjacencyEngine().Evaluate(source, candidates, tolModelUnits);
    } catch (const std::exception& e) {
        CRookServer::SendError(res, std::string("evaluate_failed: ") + e.what());
        return;
    } catch (...) {
        CRookServer::SendError(res, "evaluate_failed: unknown");
        return;
    }

    const double areaScale = srcUnitsToMm * srcUnitsToMm;  // model area -> mm^2

    json edges = json::array();
    for (const ro::ExactEdge& e : core.edges) {
        json fps = json::array();
        for (const ro::FacePair& fp : e.facePairs) {
            fps.push_back({
                {"sourceFaceIndex", fp.sourceFaceIndex},
                {"candidateFaceIndex", fp.candidateFaceIndex},
                {"sharedArea", fp.sharedArea}
            });
        }
        edges.push_back({
            {"targetId", e.targetId},
            {"relationship", e.relationship},
            {"sharedArea", e.sharedArea},
            {"sharedAreaMm2", e.sharedArea * areaScale},
            {"facePairs", fps}
        });
    }

    json cands = json::array();
    for (const ro::ExactCandidate& c : core.candidates) {
        cands.push_back({
            {"id", c.id},
            {"capability", ro::CapabilityToString(c.capability)}
        });
    }

    json out;
    out["sourceId"]         = sourceId;
    out["sourceCapability"] = ro::CapabilityToString(core.sourceCapability);
    out["modelUnitsToMm"]   = srcUnitsToMm;
    out["fuzzMm"]           = fuzzMm;
    out["tolModelUnits"]    = tolModelUnits;
    out["edges"]            = edges;
    out["candidates"]       = cands;
    out["diagnostics"]      = core.diagnostics;

    CRookServer::SendSuccess(res, out);
}

} // namespace Handlers
} // namespace Rook
