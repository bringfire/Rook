// IntersectionHandler.cpp
//
// 6 intersection routes.
// curve-curve and curve-surface use RunScript (RhinoSdkIntersect.h is blocked).
// curve-brep, brep-brep, plane-brep use direct SDK (rhinoSdkUtilities.h).
// road/intersection/candidates uses exact native curve-curve analysis so it
// does not mutate the document during read-only candidate detection.

#include "stdafx.h"
#include "Handlers/IntersectionHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/ObjectDiffTracker.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <optional>
#include <iomanip>
#include <map>
#include <mutex>
#include <set>
#include <sstream>
#include <thread>
#include <vector>
#include <winhttp.h>

#pragma comment(lib, "winhttp.lib")

namespace Rook {
namespace Handlers {

namespace fs = std::filesystem;
extern "C" IMAGE_DOS_HEADER __ImageBase;
static const GUID g_RookRoadsPlugInId =
{ 0xa9b8c7d6, 0xe5f4, 0x3a2b, { 0x1c, 0x0d, 0x9e, 0x8f, 0x7a, 0x6b, 0x5c, 0x4d } };

// ─── Helpers ────────────────────────────────────────────────────────

static nlohmann::json Point3dToJson(const ON_3dPoint& pt)
{
    return { pt.x, pt.y, pt.z };
}

static nlohmann::json Vector3dToJson(const ON_3dVector& v)
{
    return { v.x, v.y, v.z };
}

struct RoadProfileMetadata
{
    struct Feature
    {
        std::string type;
        std::string label;
        double offset = 0.0;
        double width = 0.0;
        bool bilateral = true;
    };

    std::string name;
    bool symmetric = true;
    double totalWidth = 0.0;
    double maxOffset = 0.0;
    double carriagewayEdgeOffset = 0.0;
    double carriagewaySurfaceOffset = 0.0;
    double curbReturnDriverOffset = 0.0;
    double edgeOfPavementOffset = 0.0;
    double outerEnvelopeOffset = 0.0;
    double armLengthOuterEnvelopeMultiplier = 0.0;
    double armLengthCarriagewayMultiplier = 0.0;
    double armLengthDiagonalMultiplier = 0.0;
    double armLengthRadiusMultiplier = 0.0;
    double armLengthMin = 0.0;
    double armLengthMax = 0.0;
    bool hasUnilateralFeatures = false;
    bool requiresSideSelection = false;
    fs::path path;
    std::vector<Feature> features;
};

static double EffectiveArmLengthOuterEnvelopeMultiplier(const RoadProfileMetadata& metadata)
{
    return metadata.armLengthOuterEnvelopeMultiplier > 0.0 ? metadata.armLengthOuterEnvelopeMultiplier : 2.25;
}

static double EffectiveArmLengthCarriagewayMultiplier(const RoadProfileMetadata& metadata)
{
    return metadata.armLengthCarriagewayMultiplier > 0.0 ? metadata.armLengthCarriagewayMultiplier : 3.5;
}

static double EffectiveArmLengthDiagonalMultiplier(const RoadProfileMetadata& metadata)
{
    return metadata.armLengthDiagonalMultiplier > 0.0 ? metadata.armLengthDiagonalMultiplier : 0.72;
}

static double EffectiveArmLengthRadiusMultiplier(const RoadProfileMetadata& metadata)
{
    return metadata.armLengthRadiusMultiplier > 0.0 ? metadata.armLengthRadiusMultiplier : 2.4;
}

static double EffectiveArmLengthMin(const RoadProfileMetadata& metadata)
{
    return metadata.armLengthMin > 0.0 ? metadata.armLengthMin : 10.0;
}

static double EffectiveArmLengthMax(const RoadProfileMetadata& metadata)
{
    return metadata.armLengthMax > 0.0 ? metadata.armLengthMax : 48.0;
}

// Extract an ON_Brep* from geometry (handles Brep, Extrusion, Surface).
// Caller must delete if bMustDelete is true.
static const ON_Brep* ExtractBrep(const ON_Geometry* geom, bool& bMustDelete)
{
    bMustDelete = false;

    if (const ON_Brep* brep = ON_Brep::Cast(geom))
        return brep;

    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
    {
        ON_Brep* brep = ext->BrepForm();
        if (brep) { bMustDelete = true; return brep; }
    }

    if (const ON_Surface* srf = ON_Surface::Cast(geom))
    {
        ON_Brep* brep = srf->BrepForm();
        if (brep) { bMustDelete = true; return brep; }
    }

    return nullptr;
}

static fs::path FindProfilesRootFrom(const fs::path& start)
{
    fs::path current = start;
    while (!current.empty())
    {
        const fs::path candidate = current / "knowledge" / "roads" / "profiles";
        if (fs::exists(candidate) && fs::is_directory(candidate))
            return candidate;

        const fs::path parent = current.parent_path();
        if (parent == current)
            break;
        current = parent;
    }

    return {};
}

static fs::path TryGetModuleDirectory()
{
    wchar_t modulePath[MAX_PATH] = {};
    const HMODULE instance = reinterpret_cast<HMODULE>(&__ImageBase);
    const DWORD copied = ::GetModuleFileNameW(instance, modulePath, MAX_PATH);
    if (copied == 0 || copied >= MAX_PATH)
        return {};

    return fs::path(modulePath).parent_path();
}

static fs::path TryGetEnvironmentPath(const wchar_t* name)
{
    if (!name || !*name)
        return {};

    wchar_t* value = nullptr;
    size_t len = 0;
    if (_wdupenv_s(&value, &len, name) != 0 || value == nullptr || len == 0)
        return {};

    fs::path result(value);
    free(value);
    return result;
}

static fs::path ResolveProfilesRoot()
{
    std::vector<fs::path> searched;

    const auto tryDirectCandidate = [&searched](const fs::path& root) -> fs::path
    {
        if (root.empty())
            return {};

        const fs::path candidate = root / "knowledge" / "roads" / "profiles";
        searched.push_back(candidate);
        if (fs::exists(candidate) && fs::is_directory(candidate))
            return candidate;

        return {};
    };

    const auto tryWalkUpCandidate = [&searched](const fs::path& start) -> fs::path
    {
        if (start.empty())
            return {};

        fs::path current = start;
        while (!current.empty())
        {
            const fs::path candidate = current / "knowledge" / "roads" / "profiles";
            searched.push_back(candidate);
            if (fs::exists(candidate) && fs::is_directory(candidate))
                return candidate;

            const fs::path parent = current.parent_path();
            if (parent == current)
                break;
            current = parent;
        }

        return {};
    };

    const fs::path moduleDir = TryGetModuleDirectory();
    if (const fs::path root = tryDirectCandidate(moduleDir); !root.empty())
        return root;
    if (const fs::path root = tryWalkUpCandidate(moduleDir); !root.empty())
        return root;

    try
    {
        const fs::path cwd = fs::current_path();
        if (const fs::path root = tryDirectCandidate(cwd); !root.empty())
            return root;
        if (const fs::path root = tryWalkUpCandidate(cwd); !root.empty())
            return root;
    }
    catch (...)
    {
    }

    const fs::path envRoot = TryGetEnvironmentPath(L"ROOK_ROOT");
    if (const fs::path root = tryDirectCandidate(envRoot); !root.empty())
        return root;
    if (const fs::path root = tryWalkUpCandidate(envRoot); !root.empty())
        return root;

    std::string message = "Could not locate knowledge/roads/profiles. Searched:";
    for (const auto& candidate : searched)
    {
        message += " ";
        message += candidate.u8string();
        message += ";";
    }

    throw std::runtime_error(message);
}

static bool IsSafeProfileName(const std::string& value)
{
    return !value.empty()
        && std::all_of(value.begin(), value.end(), [](unsigned char ch)
        {
            return std::isalnum(ch) || ch == '_' || ch == '-';
        });
}

// Load a road profile from the Rhino document's user text (RC_RoadProfileSummary:: key).
// Returns nullopt if the summary is missing, corrupt, or fails invariant checks.
// MUST be called on the main thread (accesses CRhinoDoc).
static bool TryGetDocumentUserString(
    CRhinoDoc* pDoc, const std::string& flatKey, const std::string& sectionKey, ON_wString& value)
{
    const std::vector<std::string> candidates = {
        flatKey,
        sectionKey,
    };

    for (const auto& candidate : candidates)
    {
        if (candidate.empty())
            continue;

        if (pDoc->GetUserString(Utf8ToWide(candidate), value))
            return true;
    }

    return false;
}

static std::optional<nlohmann::json> LoadDocumentJsonObject(
    CRhinoDoc* pDoc, const std::string& flatKey, const std::string& sectionKey)
{
    ON_wString value;
    if (!TryGetDocumentUserString(pDoc, flatKey, sectionKey, value))
        return std::nullopt;

    std::string json = WideToUtf8(value);
    if (json.empty())
        return std::nullopt;

    const auto parsed = nlohmann::json::parse(json, nullptr, false);
    if (parsed.is_discarded() || !parsed.is_object())
        return std::nullopt;

    return parsed;
}

static std::optional<RoadProfileMetadata> ParseRoadProfileMetadataJson(
    const nlohmann::json& j, const std::string& profileName)
{
    if (!j.is_object())
        return std::nullopt;
    if (!j.contains("features") || !j["features"].is_array())
        return std::nullopt;

    RoadProfileMetadata metadata;
    metadata.name = j.value("name", profileName);
    metadata.symmetric = j.value("symmetric", true);
    metadata.totalWidth = j.value("totalWidth", 0.0);

    bool hasCarriagewayEdge = false;
    bool hasCurbReturnDriver = false;
    bool hasOuterEnvelope = false;
    for (const auto& feature : j["features"])
    {
        if (!feature.is_object())
            continue;

        RoadProfileMetadata::Feature featureMetadata;
        featureMetadata.type = feature.value("type", std::string());
        featureMetadata.label = feature.value("label", featureMetadata.type);
        featureMetadata.offset = feature.value("offset", 0.0);
        featureMetadata.width = feature.value("width", 0.0);
        featureMetadata.bilateral = feature.value("bilateral", true);
        metadata.features.push_back(featureMetadata);

        const double offset = featureMetadata.offset;
        metadata.maxOffset = (std::max)(metadata.maxOffset, std::fabs(offset));

        const std::string& type = featureMetadata.type;
        if (type == "carriageway_edge")
        {
            hasCarriagewayEdge = true;
            metadata.carriagewayEdgeOffset = (std::max)(metadata.carriagewayEdgeOffset, std::fabs(offset));
            metadata.carriagewaySurfaceOffset = (std::max)(metadata.carriagewaySurfaceOffset, std::fabs(offset));
            metadata.curbReturnDriverOffset = (std::max)(metadata.curbReturnDriverOffset, std::fabs(offset));
            hasCurbReturnDriver = true;
        }
        else if (type == "edge_of_pavement")
        {
            metadata.edgeOfPavementOffset = (std::max)(metadata.edgeOfPavementOffset, std::fabs(offset));
            metadata.carriagewaySurfaceOffset = (std::max)(metadata.carriagewaySurfaceOffset, std::fabs(offset));
        }
        else if (type == "curb_face")
        {
            metadata.carriagewaySurfaceOffset = (std::max)(metadata.carriagewaySurfaceOffset, std::fabs(offset));
            metadata.curbReturnDriverOffset = (std::max)(metadata.curbReturnDriverOffset, std::fabs(offset));
            hasCurbReturnDriver = true;
        }

        if (type == "row")
        {
            metadata.outerEnvelopeOffset = (std::max)(metadata.outerEnvelopeOffset, std::fabs(offset));
            hasOuterEnvelope = true;
        }

        if (!featureMetadata.bilateral)
            metadata.hasUnilateralFeatures = true;
    }

    const bool hasAnySurfaceBoundary = hasCarriagewayEdge || metadata.carriagewaySurfaceOffset > 0.0;
    if (!hasAnySurfaceBoundary)
        return std::nullopt;

    if (metadata.maxOffset <= 0.0)
        return std::nullopt;

    if (metadata.totalWidth <= 0.0)
        metadata.totalWidth = metadata.maxOffset * 2.0;

    if (metadata.carriagewaySurfaceOffset <= 0.0)
        metadata.carriagewaySurfaceOffset = metadata.carriagewayEdgeOffset;

    if (!hasCurbReturnDriver || metadata.curbReturnDriverOffset <= 0.0)
        metadata.curbReturnDriverOffset = metadata.carriagewaySurfaceOffset;

    if (!hasOuterEnvelope || metadata.outerEnvelopeOffset <= 0.0)
        metadata.outerEnvelopeOffset = metadata.maxOffset;

    if (j.contains("intersectionDefaults") && j["intersectionDefaults"].is_object())
    {
        const auto& defaults = j["intersectionDefaults"];
        metadata.armLengthOuterEnvelopeMultiplier = defaults.value("armLengthOuterEnvelopeMultiplier", 0.0);
        metadata.armLengthCarriagewayMultiplier = defaults.value("armLengthCarriagewayMultiplier", 0.0);
        metadata.armLengthDiagonalMultiplier = defaults.value("armLengthDiagonalMultiplier", 0.0);
        metadata.armLengthRadiusMultiplier = defaults.value("armLengthRadiusMultiplier", 0.0);
        metadata.armLengthMin = defaults.value("armLengthMin", 0.0);
        metadata.armLengthMax = defaults.value("armLengthMax", 0.0);
    }

    metadata.requiresSideSelection = !metadata.symmetric && metadata.hasUnilateralFeatures;
    return metadata;
}

static std::optional<RoadProfileMetadata> LoadRoadProfileFromDocument(
    CRhinoDoc* pDoc, const std::string& profileName)
{
    const std::string flatKey = "RC_RoadProfileSummary::" + profileName;
    const std::string sectionKey = "RC_RoadProfileSummary\\" + profileName;
    auto parsed = LoadDocumentJsonObject(pDoc, flatKey, sectionKey);
    if (!parsed.has_value())
        return std::nullopt;

    const auto& j = parsed.value();
    if (j.is_discarded() || !j.is_object())
        return std::nullopt;
    if (j.value("schema", std::string()) != "roadcreator.road-profile-summary/v1")
        return std::nullopt;

    RoadProfileMetadata metadata;
    metadata.name = j.value("name", profileName);
    metadata.symmetric = j.value("symmetric", true);
    metadata.totalWidth = j.value("totalWidth", 0.0);
    metadata.maxOffset = j.value("maxOffset", 0.0);
    metadata.carriagewayEdgeOffset = j.value("carriagewayEdgeOffset", 0.0);
    metadata.carriagewaySurfaceOffset = j.value("carriagewaySurfaceOffset", 0.0);
    metadata.curbReturnDriverOffset = j.value("curbReturnDriverOffset", 0.0);
    metadata.edgeOfPavementOffset = j.value("edgeOfPavementOffset", 0.0);
    metadata.outerEnvelopeOffset = j.value("outerEnvelopeOffset", 0.0);
    metadata.hasUnilateralFeatures = j.value("hasUnilateralFeatures", false);
    metadata.requiresSideSelection = j.value("requiresSideSelection", false);

    // Backward-compatibility for older v1 summaries written before the
    // edge_of_pavement fallback was added on the C# side.
    if (metadata.carriagewaySurfaceOffset <= 0.0 && metadata.edgeOfPavementOffset > 0.0)
        metadata.carriagewaySurfaceOffset = metadata.edgeOfPavementOffset;
    if (metadata.carriagewayEdgeOffset <= 0.0 && metadata.carriagewaySurfaceOffset > 0.0)
        metadata.carriagewayEdgeOffset = metadata.carriagewaySurfaceOffset;
    if (metadata.curbReturnDriverOffset <= 0.0 && metadata.carriagewaySurfaceOffset > 0.0)
        metadata.curbReturnDriverOffset = metadata.carriagewaySurfaceOffset;
    if (metadata.outerEnvelopeOffset <= 0.0 && metadata.maxOffset > 0.0)
        metadata.outerEnvelopeOffset = metadata.maxOffset;

    // Validate invariants — same spirit as filesystem loader.
    // If summary is corrupt/incomplete, return nullopt to trigger filesystem fallback.
    if (metadata.maxOffset <= 0.0)
        return std::nullopt;
    if (metadata.carriagewaySurfaceOffset <= 0.0 && metadata.carriagewayEdgeOffset <= 0.0)
        return std::nullopt;
    if (metadata.totalWidth <= 0.0)
        metadata.totalWidth = metadata.maxOffset * 2.0;

    if (j.contains("features") && j["features"].is_array())
    {
        for (const auto& f : j["features"])
        {
            if (!f.is_object())
                continue;
            RoadProfileMetadata::Feature feat;
            feat.type = f.value("type", std::string());
            feat.label = f.value("label", feat.type);
            feat.offset = f.value("offset", 0.0);
            feat.width = f.value("width", 0.0);
            feat.bilateral = f.value("bilateral", true);
            metadata.features.push_back(feat);
        }
    }

    if (j.contains("intersectionDefaults") && j["intersectionDefaults"].is_object())
    {
        const auto& d = j["intersectionDefaults"];
        metadata.armLengthOuterEnvelopeMultiplier = d.value("armLengthOuterEnvelopeMultiplier", 0.0);
        metadata.armLengthCarriagewayMultiplier = d.value("armLengthCarriagewayMultiplier", 0.0);
        metadata.armLengthDiagonalMultiplier = d.value("armLengthDiagonalMultiplier", 0.0);
        metadata.armLengthRadiusMultiplier = d.value("armLengthRadiusMultiplier", 0.0);
        metadata.armLengthMin = d.value("armLengthMin", 0.0);
        metadata.armLengthMax = d.value("armLengthMax", 0.0);
    }

    return metadata;
}

// Load a canonical road profile from the Rhino document string table
// (RC_RoadProfile:: key) and derive native metadata from its feature list.
static std::optional<RoadProfileMetadata> LoadCanonicalRoadProfileFromDocument(
    CRhinoDoc* pDoc, const std::string& profileName)
{
    const std::string flatKey = "RC_RoadProfile::" + profileName;
    const std::string sectionKey = "RC_RoadProfile\\" + profileName;
    auto parsed = LoadDocumentJsonObject(pDoc, flatKey, sectionKey);
    if (!parsed.has_value())
        return std::nullopt;

    return ParseRoadProfileMetadataJson(parsed.value(), profileName);
}

// Load a road profile from filesystem (knowledge/roads/profiles/<name>.json).
// This is the legacy path for hand-authored profiles.
static RoadProfileMetadata LoadRoadProfileFromFilesystem(const std::string& profileName)
{
    const fs::path profilePath = ResolveProfilesRoot() / (profileName + ".json");
    if (!fs::exists(profilePath))
        throw std::invalid_argument("Road profile not found: " + profileName);

    std::ifstream in(profilePath);
    if (!in.is_open())
        throw std::runtime_error("Failed to open road profile: " + profileName);

    const nlohmann::json j = nlohmann::json::parse(in, nullptr, true, true);
    auto metadata = ParseRoadProfileMetadataJson(j, profileName);
    if (!metadata.has_value())
        throw std::invalid_argument(
            "Road profile must define at least one carriageway surface feature "
            "(carriageway_edge, edge_of_pavement, or curb_face): " + profileName);

    metadata->path = profilePath;
    return std::move(metadata.value());
}

// Load a road profile: try document user text first, fall back to filesystem.
// MUST be called on the main thread (reads CRhinoDoc user strings).
static RoadProfileMetadata LoadRoadProfileMetadata(
    CRhinoDoc* pDoc, const std::string& profileName)
{
    if (!IsSafeProfileName(profileName))
        throw std::invalid_argument("Invalid profile name: " + profileName);

    if (pDoc)
    {
        auto docProfile = LoadRoadProfileFromDocument(pDoc, profileName);
        if (docProfile.has_value())
            return std::move(docProfile.value());

        auto canonicalDocProfile = LoadCanonicalRoadProfileFromDocument(pDoc, profileName);
        if (canonicalDocProfile.has_value())
            return std::move(canonicalDocProfile.value());
    }

    return LoadRoadProfileFromFilesystem(profileName);
}

static nlohmann::json RoadProfileMetadataToJson(const RoadProfileMetadata& metadata)
{
    nlohmann::json j;
    j["name"] = metadata.name;
    j["symmetric"] = metadata.symmetric;
    j["totalWidth"] = RoundTo(metadata.totalWidth, 4);
    j["maxOffset"] = RoundTo(metadata.maxOffset, 4);
    j["carriagewayEdgeOffset"] = RoundTo(metadata.carriagewayEdgeOffset, 4);
    j["carriagewaySurfaceOffset"] = RoundTo(metadata.carriagewaySurfaceOffset, 4);
    j["curbReturnDriverOffset"] = RoundTo(metadata.curbReturnDriverOffset, 4);
    j["edgeOfPavementOffset"] = RoundTo(metadata.edgeOfPavementOffset, 4);
    j["outerEnvelopeOffset"] = RoundTo(metadata.outerEnvelopeOffset, 4);
    const double armLengthOuterEnvelopeMultiplier = EffectiveArmLengthOuterEnvelopeMultiplier(metadata);
    const double armLengthCarriagewayMultiplier = EffectiveArmLengthCarriagewayMultiplier(metadata);
    const double armLengthDiagonalMultiplier = EffectiveArmLengthDiagonalMultiplier(metadata);
    const double armLengthRadiusMultiplier = EffectiveArmLengthRadiusMultiplier(metadata);
    const double armLengthMin = EffectiveArmLengthMin(metadata);
    const double armLengthMax = EffectiveArmLengthMax(metadata);

    j["armLengthOuterEnvelopeMultiplier"] = RoundTo(armLengthOuterEnvelopeMultiplier, 4);
    j["armLengthCarriagewayMultiplier"] = RoundTo(armLengthCarriagewayMultiplier, 4);
    j["armLengthDiagonalMultiplier"] = RoundTo(armLengthDiagonalMultiplier, 4);
    j["armLengthRadiusMultiplier"] = RoundTo(armLengthRadiusMultiplier, 4);
    j["armLengthMin"] = RoundTo(armLengthMin, 4);
    j["armLengthMax"] = RoundTo(armLengthMax, 4);

    nlohmann::json defaults;
    defaults["armLengthOuterEnvelopeMultiplier"] = RoundTo(armLengthOuterEnvelopeMultiplier, 4);
    defaults["armLengthCarriagewayMultiplier"] = RoundTo(armLengthCarriagewayMultiplier, 4);
    defaults["armLengthDiagonalMultiplier"] = RoundTo(armLengthDiagonalMultiplier, 4);
    defaults["armLengthRadiusMultiplier"] = RoundTo(armLengthRadiusMultiplier, 4);
    defaults["armLengthMin"] = RoundTo(armLengthMin, 4);
    defaults["armLengthMax"] = RoundTo(armLengthMax, 4);
    j["intersectionDefaults"] = std::move(defaults);

    j["requiresSideSelection"] = metadata.requiresSideSelection;
    return j;
}

static bool RequiresExplicitAsymmetricSide(
    const RoadProfileMetadata* metadata,
    const std::string& asymmetricSide)
{
    return metadata != nullptr && metadata->requiresSideSelection && asymmetricSide.empty();
}

static nlohmann::json BuildRequiredSideSelectionsJson(
    const RoadProfileMetadata* metadataA,
    const std::string& asymmetricSideA,
    const RoadProfileMetadata* metadataB,
    const std::string& asymmetricSideB)
{
    nlohmann::json required = nlohmann::json::array();

    auto appendRoad = [&required](const char* roadLabel, const RoadProfileMetadata* metadata)
    {
        nlohmann::json entry;
        entry["road"] = roadLabel;
        entry["profileName"] = metadata ? metadata->name : "";
        entry["options"] = nlohmann::json::array({ "left", "right" });
        entry["provided"] = nullptr;
        entry["message"] =
            "Profile " + (metadata ? metadata->name : std::string("(unknown)"))
            + " has unilateral features and requires an explicit side selection for road "
            + roadLabel + ".";
        required.push_back(std::move(entry));
    };

    if (RequiresExplicitAsymmetricSide(metadataA, asymmetricSideA))
        appendRoad("A", metadataA);
    if (RequiresExplicitAsymmetricSide(metadataB, asymmetricSideB))
        appendRoad("B", metadataB);

    return required;
}

// Clear selection, then select specific objects by UUID.
static void SelectObjects(CRhinoDoc* pDoc, const std::vector<ON_UUID>& ids)
{
    CRhinoObjectIterator clearIt(*pDoc,
        CRhinoObjectIterator::normal_or_locked_objects,
        CRhinoObjectIterator::active_objects);
    for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
        const_cast<CRhinoObject*>(o)->Select(false);

    for (const auto& id : ids)
    {
        const CRhinoObject* obj = pDoc->LookupObject(id);
        if (obj)
            const_cast<CRhinoObject*>(obj)->Select(true);
    }
}

static double ComputeCurveLengthToParameter(const ON_Curve& curve, double parameter)
{
    double totalLength = 0.0;
    curve.GetLength(&totalLength);

    const ON_Interval domain = curve.Domain();
    if (parameter <= domain.Min())
        return 0.0;
    if (parameter >= domain.Max())
        return totalLength;

    std::unique_ptr<ON_Curve> prefix(curve.DuplicateCurve());
    if (!prefix)
        return 0.0;

    if (!prefix->Trim(ON_Interval(domain.Min(), parameter)))
        return 0.0;

    double prefixLength = 0.0;
    prefix->GetLength(&prefixLength);
    return prefixLength;
}

static double ComputeAcuteAngleDegrees(ON_3dVector a, ON_3dVector b)
{
    if (!a.Unitize() || !b.Unitize())
        return 0.0;

    double dot = a * b;
    if (dot > 1.0) dot = 1.0;
    if (dot < -1.0) dot = -1.0;

    const double radians = std::acos(std::fabs(dot));
    return radians * 180.0 / ON_PI;
}

static bool NearlyEqualPoints(const ON_3dPoint& a, const ON_3dPoint& b, double tolerance)
{
    return a.DistanceTo(b) <= tolerance;
}

struct IntersectionCandidateInfo
{
    ON_3dPoint point = ON_3dPoint::Origin;
    ON_3dVector tangentA = ON_3dVector::XAxis;
    ON_3dVector tangentB = ON_3dVector::YAxis;
    double parameterA = 0.0;
    double parameterB = 0.0;
    double stationA = 0.0;
    double stationB = 0.0;
    double normalizedStationA = 0.0;
    double normalizedStationB = 0.0;
    double angleDegrees = 0.0;
    double endClearanceA = 0.0;
    double endClearanceB = 0.0;
    double requiredClearanceA = 0.0;
    double requiredClearanceB = 0.0;
    double score = 0.0;
    std::string reason;
};

struct CandidateComputationResult
{
    std::vector<IntersectionCandidateInfo> candidates;
    int overlapCount = 0;
    double tolerance = 0.0;
    double overlapTolerance = 0.0;
    std::string recommendedCandidateId;
};

struct CachedIntersectionAnalyzeRequest
{
    unsigned int docSn = 0;
    nlohmann::json body;
    std::chrono::steady_clock::time_point storedAt;
};

static std::mutex g_cachedIntersectionAnalyzeRequestsMutex;
static std::map<std::string, CachedIntersectionAnalyzeRequest> g_cachedIntersectionAnalyzeRequests;

static void PruneCachedIntersectionAnalyzeRequestsLocked()
{
    const auto now = std::chrono::steady_clock::now();
    for (auto it = g_cachedIntersectionAnalyzeRequests.begin(); it != g_cachedIntersectionAnalyzeRequests.end();)
    {
        if (now - it->second.storedAt > std::chrono::minutes(30))
            it = g_cachedIntersectionAnalyzeRequests.erase(it);
        else
            ++it;
    }

    while (g_cachedIntersectionAnalyzeRequests.size() > 64)
        g_cachedIntersectionAnalyzeRequests.erase(g_cachedIntersectionAnalyzeRequests.begin());
}

static void CacheIntersectionAnalyzeRequest(
    const std::string& analysisToken,
    unsigned int docSn,
    const nlohmann::json& body)
{
    if (analysisToken.empty())
        return;

    std::lock_guard<std::mutex> lock(g_cachedIntersectionAnalyzeRequestsMutex);
    g_cachedIntersectionAnalyzeRequests[analysisToken] = CachedIntersectionAnalyzeRequest{
        docSn,
        body,
        std::chrono::steady_clock::now()
    };
    PruneCachedIntersectionAnalyzeRequestsLocked();
}

static bool TryGetCachedIntersectionAnalyzeRequest(
    const std::string& analysisToken,
    CachedIntersectionAnalyzeRequest& entry)
{
    std::lock_guard<std::mutex> lock(g_cachedIntersectionAnalyzeRequestsMutex);
    PruneCachedIntersectionAnalyzeRequestsLocked();

    const auto it = g_cachedIntersectionAnalyzeRequests.find(analysisToken);
    if (it == g_cachedIntersectionAnalyzeRequests.end())
        return false;

    entry = it->second;
    return true;
}

static bool JsonBoolValueOrDefault(
    const nlohmann::json& object,
    const char* key,
    bool defaultValue)
{
    if (!object.is_object())
        return defaultValue;

    const auto it = object.find(key);
    if (it == object.end() || it->is_null())
        return defaultValue;

    if (!it->is_boolean())
        throw std::invalid_argument(std::string(key) + " must be a boolean when present");

    return it->get<bool>();
}

static nlohmann::json ComputeRoadIntersectionAnalyzeForCommit(
    unsigned int docSn,
    const nlohmann::json& body,
    ON_UUID centerlineA,
    ON_UUID centerlineB,
    const std::string& asymmetricSideA,
    const std::string& asymmetricSideB,
    double toleranceOverride,
    double overlapToleranceOverride,
    const std::vector<double>& filletRadii,
    const RoadProfileMetadata* metadataA,
    const RoadProfileMetadata* metadataB);

static WriteResult CommitRoadIntersectionNative(
    unsigned int analysisDocSn,
    const nlohmann::json& analysis,
    const std::string& analysisToken,
    const std::string& targetLayerRoot,
    const std::string& namePrefix);

struct ResolvedFeature
{
    std::string road;
    std::string side;
    std::string featureId;
    std::string type;
    std::string label;
    double offset = 0.0;
    double width = 0.0;
    bool bilateral = true;
    bool present = true;
    bool sideResolved = true;
    std::string note;
};

struct ArmInfo
{
    std::string armId;
    std::string road;
    std::string directionTag;
    ON_3dVector direction = ON_3dVector::XAxis;
    double angleRadians = 0.0;
};

struct BoundaryFeatureResolution
{
    const ResolvedFeature* feature = nullptr;
    std::string mode;
    std::string reason;
    bool exactBoundaryRole = false;
};

struct BoundaryCornerRecord
{
    bool hasCornerPairing = false;
    nlohmann::json cornerPairing;
    bool hasBoundaryIncoming = false;
    nlohmann::json boundaryIncoming;
    bool hasBoundaryOutgoing = false;
    nlohmann::json boundaryOutgoing;
};

struct BoundaryLine2D
{
    ON_2dPoint point = ON_2dPoint::Origin;
    ON_2dVector direction = ON_2dVector::XAxis;
};

static std::string NormalizeSideToken(const std::string& value)
{
    std::string normalized;
    normalized.reserve(value.size());
    for (unsigned char ch : value)
        normalized.push_back(static_cast<char>(std::tolower(ch)));

    if (normalized == "left" || normalized == "right")
        return normalized;

    return {};
}

static std::string NormalizeCandidateModeToken(const std::string& value)
{
    std::string normalized;
    normalized.reserve(value.size());
    for (unsigned char ch : value)
        normalized.push_back(static_cast<char>(std::tolower(ch)));

    if (normalized.empty() || normalized == "single")
        return "single";
    if (normalized == "all")
        return "all";

    return {};
}

static bool HasExplicitCandidateSelector(const nlohmann::json& body)
{
    return body.contains("candidateId")
        || body.contains("selectionPoint")
        || body.contains("stationHintA")
        || body.contains("stationHintB");
}

static nlohmann::json MakeUnresolvedCondition(
    const std::string& code,
    const std::string& severity,
    const std::string& message)
{
    nlohmann::json j;
    j["code"] = code;
    j["severity"] = severity;
    j["message"] = message;
    return j;
}

static void AppendUnresolvedCondition(
    nlohmann::json& unresolvedConditions,
    std::set<std::string>* dedupeKeys,
    const std::string& code,
    const std::string& severity,
    const std::string& message,
    const std::string& dedupeKey = std::string())
{
    if (dedupeKeys)
    {
        const std::string& key = dedupeKey.empty() ? message : dedupeKey;
        if (!dedupeKeys->insert(key).second)
            return;
    }

    unresolvedConditions.push_back(MakeUnresolvedCondition(code, severity, message));
}

static uint64_t Fnv1aInit()
{
    return 14695981039346656037ull;
}

static void Fnv1aAppendBytes(uint64_t& hash, const void* data, size_t size)
{
    const auto* bytes = static_cast<const unsigned char*>(data);
    for (size_t i = 0; i < size; ++i)
    {
        hash ^= static_cast<uint64_t>(bytes[i]);
        hash *= 1099511628211ull;
    }
}

static void Fnv1aAppendString(uint64_t& hash, const std::string& value)
{
    Fnv1aAppendBytes(hash, value.data(), value.size());
    const unsigned char sep = 0xff;
    Fnv1aAppendBytes(hash, &sep, 1);
}

static void Fnv1aAppendDouble(uint64_t& hash, double value)
{
    const double rounded = RoundTo(value, 6);
    Fnv1aAppendBytes(hash, &rounded, sizeof(rounded));
}

static std::string HashToHex(uint64_t hash)
{
    std::ostringstream oss;
    oss << std::hex << std::setfill('0') << std::setw(16) << hash;
    return oss.str();
}

static std::string BuildCurveSignature(const ON_Curve& curve)
{
    double length = 0.0;
    curve.GetLength(&length);

    const ON_Interval domain = curve.Domain();
    const ON_BoundingBox bbox = curve.BoundingBox();
    const ON_3dPoint start = curve.PointAtStart();
    const ON_3dPoint end = curve.PointAtEnd();
    const ON_3dPoint mid = curve.PointAt(domain.ParameterAt(0.5));

    uint64_t hash = Fnv1aInit();
    Fnv1aAppendDouble(hash, length);
    Fnv1aAppendDouble(hash, domain.Min());
    Fnv1aAppendDouble(hash, domain.Max());
    Fnv1aAppendDouble(hash, bbox.m_min.x);
    Fnv1aAppendDouble(hash, bbox.m_min.y);
    Fnv1aAppendDouble(hash, bbox.m_min.z);
    Fnv1aAppendDouble(hash, bbox.m_max.x);
    Fnv1aAppendDouble(hash, bbox.m_max.y);
    Fnv1aAppendDouble(hash, bbox.m_max.z);
    Fnv1aAppendDouble(hash, start.x);
    Fnv1aAppendDouble(hash, start.y);
    Fnv1aAppendDouble(hash, start.z);
    Fnv1aAppendDouble(hash, mid.x);
    Fnv1aAppendDouble(hash, mid.y);
    Fnv1aAppendDouble(hash, mid.z);
    Fnv1aAppendDouble(hash, end.x);
    Fnv1aAppendDouble(hash, end.y);
    Fnv1aAppendDouble(hash, end.z);
    return HashToHex(hash);
}

static nlohmann::json CandidateToJson(const IntersectionCandidateInfo& candidate, size_t index)
{
    nlohmann::json candidateJson;
    candidateJson["candidateId"] = "cand-" + std::to_string(index);
    candidateJson["point"] = Point3dToJson(candidate.point);
    candidateJson["angleDegrees"] = RoundTo(candidate.angleDegrees, 2);
    candidateJson["parameterA"] = candidate.parameterA;
    candidateJson["parameterB"] = candidate.parameterB;
    candidateJson["stationA"] = RoundTo(candidate.stationA, 4);
    candidateJson["stationB"] = RoundTo(candidate.stationB, 4);
    candidateJson["normalizedStationA"] = RoundTo(candidate.normalizedStationA, 4);
    candidateJson["normalizedStationB"] = RoundTo(candidate.normalizedStationB, 4);
    candidateJson["tangentA"] = Vector3dToJson(candidate.tangentA);
    candidateJson["tangentB"] = Vector3dToJson(candidate.tangentB);
    candidateJson["endClearanceA"] = RoundTo(candidate.endClearanceA, 4);
    candidateJson["endClearanceB"] = RoundTo(candidate.endClearanceB, 4);
    candidateJson["requiredClearanceA"] = RoundTo(candidate.requiredClearanceA, 4);
    candidateJson["requiredClearanceB"] = RoundTo(candidate.requiredClearanceB, 4);
    candidateJson["score"] = candidate.score;
    candidateJson["reason"] = candidate.reason;
    return candidateJson;
}

static CandidateComputationResult ComputeRoadIntersectionCandidates(
    const ON_Curve& curveA,
    const ON_Curve& curveB,
    double documentTolerance,
    double toleranceOverride,
    double overlapToleranceOverride,
    const RoadProfileMetadata* metadataA,
    const RoadProfileMetadata* metadataB)
{
    double totalLengthA = 0.0;
    double totalLengthB = 0.0;
    curveA.GetLength(&totalLengthA);
    curveB.GetLength(&totalLengthB);

    CandidateComputationResult result;
    result.tolerance = toleranceOverride > 0.0 ? toleranceOverride : (std::max)(documentTolerance, 1e-6);
    result.overlapTolerance = overlapToleranceOverride > 0.0 ? overlapToleranceOverride : result.tolerance;

    ON_SimpleArray<ON_X_EVENT> events;
    const int eventCount = curveA.IntersectCurve(
        &curveB,
        events,
        result.tolerance,
        result.overlapTolerance,
        nullptr,
        nullptr);
    if (eventCount < 0)
        throw std::runtime_error("Exact native curve-curve intersection failed");

    result.candidates.reserve(events.Count());
    for (int i = 0; i < events.Count(); ++i)
    {
        const ON_X_EVENT& event = events[i];
        if (event.m_type == ON_X_EVENT::ccx_overlap)
        {
            ++result.overlapCount;
            continue;
        }

        if (event.m_type != ON_X_EVENT::ccx_point)
            continue;

        IntersectionCandidateInfo candidate;
        candidate.parameterA = event.m_a[0];
        candidate.parameterB = event.m_b[0];
        candidate.point = ON_3dPoint(
            0.5 * (event.m_A[0].x + event.m_B[0].x),
            0.5 * (event.m_A[0].y + event.m_B[0].y),
            0.5 * (event.m_A[0].z + event.m_B[0].z));
        candidate.tangentA = curveA.TangentAt(candidate.parameterA);
        candidate.tangentB = curveB.TangentAt(candidate.parameterB);
        candidate.stationA = ComputeCurveLengthToParameter(curveA, candidate.parameterA);
        candidate.stationB = ComputeCurveLengthToParameter(curveB, candidate.parameterB);
        candidate.normalizedStationA =
            totalLengthA > 1e-9 ? candidate.stationA / totalLengthA : 0.0;
        candidate.normalizedStationB =
            totalLengthB > 1e-9 ? candidate.stationB / totalLengthB : 0.0;
        candidate.angleDegrees = ComputeAcuteAngleDegrees(candidate.tangentA, candidate.tangentB);
        candidate.endClearanceA =
            (std::min)(candidate.stationA, (std::max)(0.0, totalLengthA - candidate.stationA));
        candidate.endClearanceB =
            (std::min)(candidate.stationB, (std::max)(0.0, totalLengthB - candidate.stationB));
        candidate.requiredClearanceA =
            metadataA ? (std::max)(metadataA->maxOffset, metadataA->carriagewayEdgeOffset) : 0.0;
        candidate.requiredClearanceB =
            metadataB ? (std::max)(metadataB->maxOffset, metadataB->carriagewayEdgeOffset) : 0.0;

        const double angleBias =
            1.0 - (std::min)(std::fabs(90.0 - candidate.angleDegrees), 90.0) / 90.0;
        const double meanNormalizedStation =
            (candidate.normalizedStationA + candidate.normalizedStationB) * 0.5;
        const double midpointBias =
            (std::max)(0.0, 1.0 - 2.0 * std::fabs(0.5 - meanNormalizedStation));

        const double clearanceBiasA = candidate.requiredClearanceA > 1e-9
            ? (std::min)(candidate.endClearanceA / candidate.requiredClearanceA, 1.0)
            : 1.0;
        const double clearanceBiasB = candidate.requiredClearanceB > 1e-9
            ? (std::min)(candidate.endClearanceB / candidate.requiredClearanceB, 1.0)
            : 1.0;
        const double clearanceBias = (std::min)(clearanceBiasA, clearanceBiasB);

        const bool hasProfileInfluence = (metadataA != nullptr || metadataB != nullptr);
        candidate.score = hasProfileInfluence
            ? RoundTo(0.55 * angleBias + 0.20 * midpointBias + 0.25 * clearanceBias, 4)
            : RoundTo(0.7 * angleBias + 0.3 * midpointBias, 4);
        candidate.reason = hasProfileInfluence
            ? "Heuristic score favors near-orthogonal crossings with adequate end clearance for the supplied road profiles."
            : "Heuristic score favors near-orthogonal crossings closer to the middle of both curves.";

        result.candidates.push_back(std::move(candidate));
    }

    std::sort(result.candidates.begin(), result.candidates.end(),
        [](const IntersectionCandidateInfo& lhs, const IntersectionCandidateInfo& rhs)
        {
            if (lhs.stationA != rhs.stationA)
                return lhs.stationA < rhs.stationA;
            return lhs.stationB < rhs.stationB;
        });

    std::vector<ON_3dPoint> uniquePoints;
    std::vector<IntersectionCandidateInfo> dedupedCandidates;
    uniquePoints.reserve(result.candidates.size());
    dedupedCandidates.reserve(result.candidates.size());
    for (const auto& candidate : result.candidates)
    {
        bool duplicate = false;
        for (const auto& point : uniquePoints)
        {
            if (NearlyEqualPoints(candidate.point, point, result.tolerance))
            {
                duplicate = true;
                break;
            }
        }

        if (!duplicate)
        {
            uniquePoints.push_back(candidate.point);
            dedupedCandidates.push_back(candidate);
        }
    }
    result.candidates = std::move(dedupedCandidates);

    if (result.candidates.size() == 1)
        result.candidates[0].reason = "Only intersection candidate found.";

    double bestScore = -1.0;
    double secondBestScore = -1.0;
    int bestIndex = -1;
    for (size_t i = 0; i < result.candidates.size(); ++i)
    {
        const double score = result.candidates[i].score;
        if (score > bestScore)
        {
            secondBestScore = bestScore;
            bestScore = score;
            bestIndex = static_cast<int>(i);
        }
        else if (score > secondBestScore)
        {
            secondBestScore = score;
        }
    }

    if (result.candidates.size() == 1)
    {
        result.recommendedCandidateId = "cand-0";
    }
    else if (bestIndex >= 0 && (bestScore - secondBestScore) >= 0.15)
    {
        result.recommendedCandidateId = "cand-" + std::to_string(bestIndex);
    }

    return result;
}

static std::pair<size_t, std::string> SelectCandidateIndex(
    const nlohmann::json& body,
    const CandidateComputationResult& candidateResult)
{
    if (candidateResult.candidates.empty())
        throw std::invalid_argument("No intersection candidates found");

    if (body.contains("candidateId"))
    {
        if (!body["candidateId"].is_string())
            throw std::invalid_argument("candidateId must be a string");

        const std::string requested = body["candidateId"].get<std::string>();
        for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
        {
            if (requested == ("cand-" + std::to_string(i)))
                return { i, "candidateId" };
        }

        throw std::invalid_argument("Unknown candidateId: " + requested);
    }

    if (body.contains("selectionPoint"))
    {
        const ON_3dPoint selectionPoint = ParsePoint3d(body, "selectionPoint");
        size_t bestIndex = 0;
        double bestDistance = ON_DBL_MAX;
        for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
        {
            const double distance = candidateResult.candidates[i].point.DistanceTo(selectionPoint);
            if (distance < bestDistance)
            {
                bestDistance = distance;
                bestIndex = i;
            }
        }
        return { bestIndex, "selectionPoint" };
    }

    const bool hasStationHintA = body.contains("stationHintA");
    const bool hasStationHintB = body.contains("stationHintB");
    if (hasStationHintA || hasStationHintB)
    {
        const double stationHintA = hasStationHintA ? body["stationHintA"].get<double>() : 0.0;
        const double stationHintB = hasStationHintB ? body["stationHintB"].get<double>() : 0.0;
        size_t bestIndex = 0;
        double bestError = ON_DBL_MAX;
        for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
        {
            const auto& candidate = candidateResult.candidates[i];
            double error = 0.0;
            if (hasStationHintA)
                error += std::fabs(candidate.stationA - stationHintA);
            if (hasStationHintB)
                error += std::fabs(candidate.stationB - stationHintB);
            if (error < bestError)
            {
                bestError = error;
                bestIndex = i;
            }
        }
        return { bestIndex, hasStationHintA && hasStationHintB ? "stationHints" : (hasStationHintA ? "stationHintA" : "stationHintB") };
    }

    if (!candidateResult.recommendedCandidateId.empty())
    {
        const size_t index = static_cast<size_t>(std::stoi(candidateResult.recommendedCandidateId.substr(5)));
        return { index, "recommended" };
    }

    if (candidateResult.candidates.size() == 1)
        return { 0, "singleCandidate" };

    throw std::invalid_argument(
        "Multiple intersection candidates found; provide candidateId, selectionPoint, stationHintA, or stationHintB");
}

static nlohmann::json BuildFeatureRulesJson(
    const std::vector<ResolvedFeature>& features)
{
    nlohmann::json rules = nlohmann::json::array();
    for (const auto& feature : features)
    {
        nlohmann::json rule;
        rule["road"] = feature.road;
        rule["featureId"] = feature.featureId;
        rule["type"] = feature.type;
        rule["label"] = feature.label;
        rule["side"] = feature.side;
        rule["offset"] = RoundTo(feature.offset, 4);
        rule["width"] = RoundTo(feature.width, 4);
        rule["bilateral"] = feature.bilateral;
        rule["present"] = feature.present;
        rule["sideResolved"] = feature.sideResolved;
        rule["semanticRole"] = feature.type;
        if (!feature.note.empty())
            rule["note"] = feature.note;
        rules.push_back(std::move(rule));
    }
    return rules;
}

static std::vector<ResolvedFeature> BuildResolvedFeatures(
    const std::string& roadLabel,
    const RoadProfileMetadata* metadata,
    const std::string& asymmetricSide,
    nlohmann::json& unresolvedConditions,
    std::set<std::string>* unresolvedConditionKeys)
{
    std::vector<ResolvedFeature> features;
    if (!metadata)
        return features;

    for (size_t i = 0; i < metadata->features.size(); ++i)
    {
        const auto& source = metadata->features[i];
        auto appendFeature = [&](const std::string& side, bool present, bool sideResolved, const std::string& note)
        {
            ResolvedFeature feature;
            feature.road = roadLabel;
            feature.side = side;
            feature.featureId = roadLabel + ":" + side + ":" + source.type + ":" + std::to_string(i);
            feature.type = source.type;
            feature.label = source.label;
            feature.offset = source.offset;
            feature.width = source.width;
            feature.bilateral = source.bilateral;
            feature.present = present;
            feature.sideResolved = sideResolved;
            feature.note = note;
            features.push_back(std::move(feature));
        };

        if (metadata->symmetric || source.bilateral)
        {
            appendFeature("left", true, true, "");
            appendFeature("right", true, true, "");
            continue;
        }

        if (asymmetricSide.empty())
        {
            appendFeature("unspecified", true, false, "Unilateral feature side must be resolved before topology decisions.");
            AppendUnresolvedCondition(
                unresolvedConditions,
                unresolvedConditionKeys,
                "asymmetric_side_unresolved",
                "warning",
                "Profile " + metadata->name + " has unilateral features but no asymmetric side was supplied for road " + roadLabel + ".",
                "asymmetric_side_unresolved|" + roadLabel);
            continue;
        }

        const std::string oppositeSide = asymmetricSide == "left" ? "right" : "left";
        appendFeature(asymmetricSide, true, true, "Resolved unilateral feature side.");
        appendFeature(oppositeSide, false, true, "Feature suppressed on opposite side because profile is unilateral.");
    }

    return features;
}

static double NormalizeAngleRadians(double angle)
{
    constexpr double twoPi = 2.0 * ON_PI;
    while (angle < 0.0)
        angle += twoPi;
    while (angle >= twoPi)
        angle -= twoPi;
    return angle;
}

static std::vector<ArmInfo> BuildOrderedArms(const IntersectionCandidateInfo& candidate)
{
    auto makeArm = [](const std::string& road, const std::string& directionTag, ON_3dVector direction) -> ArmInfo
    {
        direction.z = 0.0;
        if (!direction.Unitize())
            throw std::runtime_error("Failed to unitize arm direction for intersection analysis");

        ArmInfo arm;
        arm.armId = road + ":" + directionTag;
        arm.road = road;
        arm.directionTag = directionTag;
        arm.direction = direction;
        arm.angleRadians = NormalizeAngleRadians(std::atan2(direction.y, direction.x));
        return arm;
    };

    std::vector<ArmInfo> arms;
    arms.push_back(makeArm("A", "forward", candidate.tangentA));
    arms.push_back(makeArm("A", "backward", -candidate.tangentA));
    arms.push_back(makeArm("B", "forward", candidate.tangentB));
    arms.push_back(makeArm("B", "backward", -candidate.tangentB));

    std::sort(arms.begin(), arms.end(),
        [](const ArmInfo& lhs, const ArmInfo& rhs)
        {
            if (lhs.angleRadians != rhs.angleRadians)
                return lhs.angleRadians > rhs.angleRadians;
            return lhs.armId < rhs.armId;
        });

    return arms;
}

static const ResolvedFeature* FindResolvedFeature(
    const std::vector<ResolvedFeature>& features,
    const std::string& road,
    const std::string& side,
    const std::string& type)
{
    const ResolvedFeature* best = nullptr;
    for (const auto& feature : features)
    {
        if (feature.road != road || feature.side != side || !feature.present || feature.type != type)
            continue;

        if (!best || feature.offset > best->offset)
            best = &feature;
    }

    return best;
}

// Find the best feature for curb return pairing at an intersection corner.
// Priority: carriageway_edge > curb_face > edge_of_pavement.
// This widens the legacy carriageway_edge-only lookup to support canonical profiles.
static const ResolvedFeature* FindCurbReturnFeature(
    const std::vector<ResolvedFeature>& features,
    const std::string& road,
    const std::string& side)
{
    const ResolvedFeature* bestCarriagewayEdge = nullptr;
    const ResolvedFeature* bestCurbFace = nullptr;
    const ResolvedFeature* bestEdgeOfPavement = nullptr;

    for (const auto& f : features)
    {
        if (f.road != road || f.side != side || !f.present)
            continue;

        if (f.type == "carriageway_edge")
        {
            if (!bestCarriagewayEdge || f.offset > bestCarriagewayEdge->offset)
                bestCarriagewayEdge = &f;
        }
        else if (f.type == "curb_face")
        {
            if (!bestCurbFace || f.offset > bestCurbFace->offset)
                bestCurbFace = &f;
        }
        else if (f.type == "edge_of_pavement")
        {
            if (!bestEdgeOfPavement || f.offset > bestEdgeOfPavement->offset)
                bestEdgeOfPavement = &f;
        }
    }

    if (bestCarriagewayEdge) return bestCarriagewayEdge;
    if (bestCurbFace) return bestCurbFace;
    return bestEdgeOfPavement;
}

static const ResolvedFeature* FindOuterEnvelopeFeature(
    const std::vector<ResolvedFeature>& features,
    const std::string& road,
    const std::string& side)
{
    const ResolvedFeature* best = nullptr;
    for (const auto& feature : features)
    {
        if (feature.road != road || feature.side != side || !feature.present)
            continue;

        if (!best || feature.offset > best->offset)
            best = &feature;
    }

    return best;
}

static bool IsExplicitBoundaryRole(const std::string& type)
{
    return type == "row"
        || type == "sidewalk_outer"
        || type == "ditch"
        || type == "custom";
}

static bool IsCarriagewaySurfaceBoundaryType(const std::string& type)
{
    return type == "carriageway_edge"
        || type == "edge_of_pavement"
        || type == "curb_face";
}

static BoundaryFeatureResolution ResolveBoundaryFeatureForSide(
    const std::vector<ResolvedFeature>& features,
    const std::string& road,
    const std::string& side)
{
    BoundaryFeatureResolution resolution;

    const ResolvedFeature* bestSurfaceBoundary = nullptr;
    const ResolvedFeature* bestExplicitBoundary = nullptr;
    const ResolvedFeature* bestPresent = nullptr;
    for (const auto& feature : features)
    {
        if (feature.road != road || feature.side != side || !feature.present)
            continue;

        if (!bestPresent || feature.offset > bestPresent->offset)
            bestPresent = &feature;

        if (IsCarriagewaySurfaceBoundaryType(feature.type)
            && (!bestSurfaceBoundary || feature.offset > bestSurfaceBoundary->offset))
        {
            bestSurfaceBoundary = &feature;
        }

        if (IsExplicitBoundaryRole(feature.type)
            && (!bestExplicitBoundary || feature.offset > bestExplicitBoundary->offset))
        {
            bestExplicitBoundary = &feature;
        }
    }

    if (bestSurfaceBoundary)
    {
        resolution.feature = bestSurfaceBoundary;
        resolution.mode = "carriageway_surface_boundary";
        resolution.reason = "Selected the outermost carriageway surface boundary for this side.";
        resolution.exactBoundaryRole = true;
        return resolution;
    }

    if (bestExplicitBoundary)
    {
        resolution.feature = bestExplicitBoundary;
        resolution.mode = "explicit_boundary_role";
        resolution.reason = "Selected the outermost explicit boundary role for this side.";
        resolution.exactBoundaryRole = true;
        return resolution;
    }

    if (bestPresent)
    {
        resolution.feature = bestPresent;
        resolution.mode = "outermost_present_fallback";
        resolution.reason =
            "No explicit boundary-role feature is present on this side, so the outermost present feature is being used as the interim boundary envelope.";
        resolution.exactBoundaryRole = false;
        return resolution;
    }

    resolution.mode = "missing";
    resolution.reason = "No present feature exists on this side for boundary resolution.";
    resolution.exactBoundaryRole = false;
    return resolution;
}

static nlohmann::json MakeArmFeatureKeyJson(const std::string& armId, const ResolvedFeature& feature)
{
    nlohmann::json key;
    key["armId"] = armId;
    key["road"] = feature.road;
    key["side"] = feature.side;
    key["featureId"] = feature.featureId;
    key["role"] = feature.type;
    return key;
}

static nlohmann::json BuildOrderedArmsJson(const std::vector<ArmInfo>& arms)
{
    nlohmann::json json = nlohmann::json::array();
    for (const auto& arm : arms)
    {
        nlohmann::json entry;
        entry["armId"] = arm.armId;
        entry["road"] = arm.road;
        entry["directionTag"] = arm.directionTag;
        entry["angleDegrees"] = RoundTo(arm.angleRadians * 180.0 / ON_PI, 2);
        entry["direction"] = Vector3dToJson(arm.direction);
        json.push_back(std::move(entry));
    }
    return json;
}

static nlohmann::json BuildBoundaryWalkJson(const std::vector<BoundaryCornerRecord>& cornerRecords)
{
    nlohmann::json orderedSegments = nlohmann::json::array();
    int orderIndex = 0;

    for (size_t i = 0; i < cornerRecords.size(); ++i)
    {
        const auto& record = cornerRecords[i];
        if (record.hasBoundaryIncoming)
        {
            nlohmann::json segment;
            segment["orderIndex"] = orderIndex++;
            segment["segmentType"] = "boundary_feature";
            segment["cornerOrder"] = static_cast<int>(i);
            segment["position"] = "incoming";
            segment["sourceDecisionId"] = record.boundaryIncoming.value("decisionId", "");
            segment["key"] = record.boundaryIncoming["key"];
            segment["connectTo"] = record.boundaryIncoming["connectTo"];
            segment["operation"] = record.boundaryIncoming.value("operation", "");
            if (record.boundaryIncoming.contains("boundarySelectionMode"))
                segment["boundarySelectionMode"] = record.boundaryIncoming["boundarySelectionMode"];
            orderedSegments.push_back(std::move(segment));
        }

        if (record.hasCornerPairing)
        {
            nlohmann::json segment;
            segment["orderIndex"] = orderIndex++;
            segment["segmentType"] = "curb_return";
            segment["cornerOrder"] = static_cast<int>(i);
            segment["sourceCornerOrder"] = record.cornerPairing.value("cornerOrder", static_cast<int>(i));
            segment["incoming"] = record.cornerPairing["incoming"];
            segment["outgoing"] = record.cornerPairing["outgoing"];
            segment["radius"] = record.cornerPairing["radius"];
            orderedSegments.push_back(std::move(segment));
        }

        if (record.hasBoundaryOutgoing)
        {
            nlohmann::json segment;
            segment["orderIndex"] = orderIndex++;
            segment["segmentType"] = "boundary_feature";
            segment["cornerOrder"] = static_cast<int>(i);
            segment["position"] = "outgoing";
            segment["sourceDecisionId"] = record.boundaryOutgoing.value("decisionId", "");
            segment["key"] = record.boundaryOutgoing["key"];
            segment["connectTo"] = record.boundaryOutgoing["connectTo"];
            segment["operation"] = record.boundaryOutgoing.value("operation", "");
            if (record.boundaryOutgoing.contains("boundarySelectionMode"))
                segment["boundarySelectionMode"] = record.boundaryOutgoing["boundarySelectionMode"];
            orderedSegments.push_back(std::move(segment));
        }
    }

    return orderedSegments;
}

static nlohmann::json MakeInvariantJson(
    const std::string& code,
    bool passed,
    const std::string& message)
{
    nlohmann::json invariant;
    invariant["code"] = code;
    invariant["passed"] = passed;
    invariant["message"] = message;
    return invariant;
}

static const ArmInfo* FindArmById(const std::vector<ArmInfo>& arms, const std::string& armId)
{
    for (const auto& arm : arms)
    {
        if (arm.armId == armId)
            return &arm;
    }
    return nullptr;
}

static const ResolvedFeature* FindResolvedFeatureById(
    const std::vector<ResolvedFeature>& features,
    const std::string& featureId)
{
    for (const auto& feature : features)
    {
        if (feature.featureId == featureId)
            return &feature;
    }
    return nullptr;
}

static ON_2dVector To2d(const ON_3dVector& v)
{
    return ON_2dVector(v.x, v.y);
}

static ON_2dPoint To2d(const ON_3dPoint& p)
{
    return ON_2dPoint(p.x, p.y);
}

static ON_2dVector RightNormal(const ON_2dVector& dir)
{
    return ON_2dVector(dir.y, -dir.x);
}

static ON_2dVector LeftNormal(const ON_2dVector& dir)
{
    return ON_2dVector(-dir.y, dir.x);
}

static bool TryBuildBoundaryLine2D(
    const nlohmann::json& key,
    const std::vector<ArmInfo>& orderedArms,
    const std::vector<ResolvedFeature>& resolvedFeatures,
    const ON_3dPoint& center,
    BoundaryLine2D& line)
{
    const std::string armId = key.value("armId", std::string());
    const std::string side = key.value("side", std::string());
    const std::string featureId = key.value("featureId", std::string());

    const ArmInfo* arm = FindArmById(orderedArms, armId);
    const ResolvedFeature* feature = FindResolvedFeatureById(resolvedFeatures, featureId);
    if (!arm || !feature)
        return false;

    ON_2dVector dir = To2d(arm->direction);
    const double length = dir.Length();
    if (!(length > 1e-9))
        return false;
    dir /= length;

    ON_2dVector normal;
    if (side == "right")
        normal = RightNormal(dir);
    else if (side == "left")
        normal = LeftNormal(dir);
    else
        return false;

    line.point = To2d(center) + normal * feature->offset;
    line.direction = dir;
    return true;
}

static double Cross2d(const ON_2dVector& a, const ON_2dVector& b)
{
    return a.x * b.y - a.y * b.x;
}

static bool TryIntersectLines2D(
    const BoundaryLine2D& a,
    const BoundaryLine2D& b,
    ON_2dPoint& intersection)
{
    const ON_2dVector diff = b.point - a.point;
    const double denom = Cross2d(a.direction, b.direction);
    if (std::fabs(denom) <= 1e-9)
        return false;

    const double t = Cross2d(diff, b.direction) / denom;
    intersection = a.point + a.direction * t;
    return true;
}

static bool SegmentsIntersectStrict(
    const ON_2dPoint& a0,
    const ON_2dPoint& a1,
    const ON_2dPoint& b0,
    const ON_2dPoint& b1)
{
    auto orient = [](const ON_2dPoint& p, const ON_2dPoint& q, const ON_2dPoint& r) -> double
    {
        return (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x);
    };

    const double o1 = orient(a0, a1, b0);
    const double o2 = orient(a0, a1, b1);
    const double o3 = orient(b0, b1, a0);
    const double o4 = orient(b0, b1, a1);
    const double eps = 1e-9;

    if (std::fabs(o1) <= eps || std::fabs(o2) <= eps || std::fabs(o3) <= eps || std::fabs(o4) <= eps)
        return false;

    return ((o1 > 0.0) != (o2 > 0.0)) && ((o3 > 0.0) != (o4 > 0.0));
}

static bool PolygonSelfIntersects(const std::vector<ON_2dPoint>& polygon)
{
    if (polygon.size() < 4)
        return false;

    const size_t n = polygon.size();
    for (size_t i = 0; i < n; ++i)
    {
        const ON_2dPoint& a0 = polygon[i];
        const ON_2dPoint& a1 = polygon[(i + 1) % n];

        for (size_t j = i + 1; j < n; ++j)
        {
            const size_t iNext = (i + 1) % n;
            const size_t jNext = (j + 1) % n;

            if (i == j || iNext == j || jNext == i)
                continue;
            if (i == 0 && jNext == 0)
                continue;

            if (SegmentsIntersectStrict(a0, a1, polygon[j], polygon[jNext]))
                return true;
        }
    }

    return false;
}

static double PolygonSignedArea(const std::vector<ON_2dPoint>& polygon)
{
    if (polygon.size() < 3)
        return 0.0;

    double area = 0.0;
    for (size_t i = 0; i < polygon.size(); ++i)
    {
        const ON_2dPoint& p0 = polygon[i];
        const ON_2dPoint& p1 = polygon[(i + 1) % polygon.size()];
        area += p0.x * p1.y - p1.x * p0.y;
    }
    return 0.5 * area;
}

static ON_2dPoint PolygonCentroid(const std::vector<ON_2dPoint>& polygon)
{
    const double signedArea = PolygonSignedArea(polygon);
    if (polygon.size() < 3 || std::fabs(signedArea) <= 1e-9)
        return ON_2dPoint::Origin;

    double cx = 0.0;
    double cy = 0.0;
    for (size_t i = 0; i < polygon.size(); ++i)
    {
        const ON_2dPoint& p0 = polygon[i];
        const ON_2dPoint& p1 = polygon[(i + 1) % polygon.size()];
        const double cross = p0.x * p1.y - p1.x * p0.y;
        cx += (p0.x + p1.x) * cross;
        cy += (p0.y + p1.y) * cross;
    }

    const double factor = 1.0 / (6.0 * signedArea);
    return ON_2dPoint(cx * factor, cy * factor);
}

static nlohmann::json Point2dAsPoint3Json(const ON_2dPoint& point)
{
    return nlohmann::json::array({ RoundTo(point.x, 4), RoundTo(point.y, 4), 0.0 });
}

static bool TryBuildCurbReturnArc2D(
    const nlohmann::json& pairing,
    const std::vector<ArmInfo>& orderedArms,
    const std::vector<ResolvedFeature>& resolvedFeatures,
    const ON_3dPoint& centerPoint,
    nlohmann::json& arcJson)
{
    BoundaryLine2D incomingLine;
    BoundaryLine2D outgoingLine;
    if (!TryBuildBoundaryLine2D(pairing["incoming"], orderedArms, resolvedFeatures, centerPoint, incomingLine)
        || !TryBuildBoundaryLine2D(pairing["outgoing"], orderedArms, resolvedFeatures, centerPoint, outgoingLine))
    {
        return false;
    }

    ON_2dPoint cornerPoint;
    if (!TryIntersectLines2D(incomingLine, outgoingLine, cornerPoint))
        return false;

    const double radius = pairing.value("radius", 0.0);
    if (!(radius > 1e-9))
        return false;

    ON_2dVector d1 = incomingLine.direction;
    ON_2dVector d2 = outgoingLine.direction;
    const double len1 = d1.Length();
    const double len2 = d2.Length();
    if (!(len1 > 1e-9) || !(len2 > 1e-9))
        return false;
    d1 /= len1;
    d2 /= len2;

    double dot = d1.x * d2.x + d1.y * d2.y;
    dot = (std::max)(-1.0, (std::min)(1.0, dot));
    const double theta = std::acos(dot);
    if (!(theta > 1e-6) || !(std::fabs(std::sin(theta * 0.5)) > 1e-9) || !(std::fabs(std::tan(theta * 0.5)) > 1e-9))
        return false;

    const double tangentDistance = radius / std::tan(theta * 0.5);
    const ON_2dPoint center2d(centerPoint.x, centerPoint.y);

    const ON_2dPoint t1a = cornerPoint + d1 * tangentDistance;
    const ON_2dPoint t1b = cornerPoint - d1 * tangentDistance;
    const ON_2dPoint t2a = cornerPoint + d2 * tangentDistance;
    const ON_2dPoint t2b = cornerPoint - d2 * tangentDistance;

    const ON_2dPoint tangent1 = (t1a.DistanceTo(center2d) < t1b.DistanceTo(center2d)) ? t1a : t1b;
    const ON_2dPoint tangent2 = (t2a.DistanceTo(center2d) < t2b.DistanceTo(center2d)) ? t2a : t2b;

    const ON_2dVector normals1[2] = { LeftNormal(d1), RightNormal(d1) };
    const ON_2dVector normals2[2] = { LeftNormal(d2), RightNormal(d2) };

    bool foundCenter = false;
    ON_2dPoint bestCenter = ON_2dPoint::Origin;
    double bestError = ON_DBL_MAX;
    for (const auto& n1 : normals1)
    {
        const ON_2dPoint c1 = tangent1 + n1 * radius;
        for (const auto& n2 : normals2)
        {
            const ON_2dPoint c2 = tangent2 + n2 * radius;
            const double error = c1.DistanceTo(c2);
            if (error < bestError)
            {
                bestError = error;
                bestCenter = ON_2dPoint(0.5 * (c1.x + c2.x), 0.5 * (c1.y + c2.y));
                foundCenter = true;
            }
        }
    }

    if (!foundCenter || bestError > 1e-3)
        return false;

    arcJson["cornerOrder"] = pairing.value("cornerOrder", -1);
    arcJson["radius"] = RoundTo(radius, 4);
    arcJson["cornerPoint"] = Point2dAsPoint3Json(cornerPoint);
    arcJson["startPoint"] = Point2dAsPoint3Json(tangent1);
    arcJson["endPoint"] = Point2dAsPoint3Json(tangent2);
    arcJson["center"] = Point2dAsPoint3Json(bestCenter);
    arcJson["validationError"] = RoundTo(bestError, 6);
    return true;
}

static nlohmann::json BuildPreviewGeometryJson(
    const IntersectionCandidateInfo& candidate,
    const std::vector<double>& filletRadii)
{
    nlohmann::json preview = nlohmann::json::array();

    nlohmann::json focus;
    focus["type"] = "candidate_focus";
    focus["point"] = Point3dToJson(candidate.point);
    preview.push_back(std::move(focus));

    nlohmann::json approachA;
    approachA["type"] = "approach_vector";
    approachA["road"] = "A";
    approachA["origin"] = Point3dToJson(candidate.point);
    approachA["tangent"] = Vector3dToJson(candidate.tangentA);
    approachA["station"] = RoundTo(candidate.stationA, 4);
    preview.push_back(std::move(approachA));

    nlohmann::json approachB;
    approachB["type"] = "approach_vector";
    approachB["road"] = "B";
    approachB["origin"] = Point3dToJson(candidate.point);
    approachB["tangent"] = Vector3dToJson(candidate.tangentB);
    approachB["station"] = RoundTo(candidate.stationB, 4);
    preview.push_back(std::move(approachB));

    if (candidate.requiredClearanceA > 0.0)
    {
        nlohmann::json windowA;
        windowA["type"] = "station_window";
        windowA["road"] = "A";
        windowA["stationStart"] = RoundTo((std::max)(0.0, candidate.stationA - candidate.requiredClearanceA), 4);
        windowA["stationEnd"] = RoundTo(candidate.stationA + candidate.requiredClearanceA, 4);
        windowA["requiredClearance"] = RoundTo(candidate.requiredClearanceA, 4);
        preview.push_back(std::move(windowA));
    }

    if (candidate.requiredClearanceB > 0.0)
    {
        nlohmann::json windowB;
        windowB["type"] = "station_window";
        windowB["road"] = "B";
        windowB["stationStart"] = RoundTo((std::max)(0.0, candidate.stationB - candidate.requiredClearanceB), 4);
        windowB["stationEnd"] = RoundTo(candidate.stationB + candidate.requiredClearanceB, 4);
        windowB["requiredClearance"] = RoundTo(candidate.requiredClearanceB, 4);
        preview.push_back(std::move(windowB));
    }

    if (!filletRadii.empty())
    {
        nlohmann::json filletPreview;
        filletPreview["type"] = "fillet_radii";
        filletPreview["values"] = filletRadii;
        preview.push_back(std::move(filletPreview));
    }

    return preview;
}

// ─── POST /road/intersection/candidates ───────────────────────────

void HandleRoadIntersectionCandidates(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID centerlineA;
    ON_UUID centerlineB;
    try
    {
        centerlineA = ParseUuid(body, "centerlineA");
        centerlineB = ParseUuid(body, "centerlineB");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    const std::string profileA = body.value("profileA", std::string());
    const std::string profileB = body.value("profileB", std::string());
    const double toleranceOverride = body.value("tolerance", 0.0);
    const double overlapToleranceOverride = body.value("overlapTolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn,
         centerlineA,
         centerlineB,
         toleranceOverride,
         overlapToleranceOverride,
         profileA,
         profileB]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        std::unique_ptr<RoadProfileMetadata> metadataA;
        std::unique_ptr<RoadProfileMetadata> metadataB;
        if (!profileA.empty())
            metadataA = std::make_unique<RoadProfileMetadata>(
                LoadRoadProfileMetadata(pDoc, profileA));
        if (!profileB.empty())
            metadataB = std::make_unique<RoadProfileMetadata>(
                LoadRoadProfileMetadata(pDoc, profileB));

        const CRhinoObject* objA = pDoc->LookupObject(centerlineA);
        const CRhinoObject* objB = pDoc->LookupObject(centerlineB);
        if (!objA || !objB)
            throw std::invalid_argument("One or both centerline objects not found");

        const ON_Curve* curveA = ON_Curve::Cast(objA->Geometry());
        const ON_Curve* curveB = ON_Curve::Cast(objB->Geometry());
        if (!curveA || !curveB)
            throw std::invalid_argument("Both centerline objects must be curves");

        const CandidateComputationResult candidateResult = ComputeRoadIntersectionCandidates(
            *curveA,
            *curveB,
            pDoc->AbsoluteTolerance(),
            toleranceOverride,
            overlapToleranceOverride,
            metadataA.get(),
            metadataB.get());

        nlohmann::json candidatesJson = nlohmann::json::array();
        for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
        {
            candidatesJson.push_back(CandidateToJson(candidateResult.candidates[i], i));
        }

        nlohmann::json result;
        result["centerlineA"] = UuidToString(centerlineA);
        result["centerlineB"] = UuidToString(centerlineB);
        if (metadataA)
            result["profileA"] = RoadProfileMetadataToJson(*metadataA);
        if (metadataB)
            result["profileB"] = RoadProfileMetadataToJson(*metadataB);
        result["candidateCount"] = static_cast<int>(candidateResult.candidates.size());
        result["overlapCount"] = candidateResult.overlapCount;
        result["candidates"] = std::move(candidatesJson);
        result["recommendedCandidateId"] =
            candidateResult.recommendedCandidateId.empty()
                ? nlohmann::json(nullptr)
                : nlohmann::json(candidateResult.recommendedCandidateId);
        result["analysisMode"] = "exact-native-curve-curve";
        result["intersectionTolerance"] = RoundTo(candidateResult.tolerance, 6);
        result["overlapTolerance"] = RoundTo(candidateResult.overlapTolerance, 6);
        return result;
    });

    try
    {
        nlohmann::json result = future.get();
        CacheIntersectionAnalyzeRequest(result.value("analysisToken", std::string()), docSn, body);
        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

void HandleRoadIntersectionAnalyze(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID centerlineA;
    ON_UUID centerlineB;
    try
    {
        centerlineA = ParseUuid(body, "centerlineA");
        centerlineB = ParseUuid(body, "centerlineB");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    const std::string profileA = body.value("profileA", std::string());
    const std::string profileB = body.value("profileB", std::string());
    const std::string asymmetricSideA = NormalizeSideToken(body.value("asymmetricSideA", std::string()));
    const std::string asymmetricSideB = NormalizeSideToken(body.value("asymmetricSideB", std::string()));
    if (body.contains("asymmetricSideA") && asymmetricSideA.empty())
    {
        CRookServer::SendError(res, "asymmetricSideA must be 'left' or 'right'");
        return;
    }
    if (body.contains("asymmetricSideB") && asymmetricSideB.empty())
    {
        CRookServer::SendError(res, "asymmetricSideB must be 'left' or 'right'");
        return;
    }

    std::vector<double> filletRadii;
    if (body.contains("filletRadii"))
    {
        if (!body["filletRadii"].is_array())
        {
            CRookServer::SendError(res, "filletRadii must be an array");
            return;
        }

        for (const auto& entry : body["filletRadii"])
        {
            const double radius = entry.get<double>();
            if (!std::isfinite(radius) || radius < 0.0)
            {
                CRookServer::SendError(res, "filletRadii values must be finite and non-negative");
                return;
            }
            filletRadii.push_back(RoundTo(radius, 4));
        }
    }

    const double toleranceOverride = body.value("tolerance", 0.0);
    const double overlapToleranceOverride = body.value("overlapTolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn,
         body,
         centerlineA,
         centerlineB,
         profileA,
         profileB,
         asymmetricSideA,
         asymmetricSideB,
         toleranceOverride,
         overlapToleranceOverride,
         filletRadii = std::move(filletRadii)]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        std::unique_ptr<RoadProfileMetadata> metadataA;
        std::unique_ptr<RoadProfileMetadata> metadataB;
        if (!profileA.empty())
            metadataA = std::make_unique<RoadProfileMetadata>(
                LoadRoadProfileMetadata(pDoc, profileA));
        if (!profileB.empty())
            metadataB = std::make_unique<RoadProfileMetadata>(
                LoadRoadProfileMetadata(pDoc, profileB));

        const CRhinoObject* objA = pDoc->LookupObject(centerlineA);
        const CRhinoObject* objB = pDoc->LookupObject(centerlineB);
        if (!objA || !objB)
            throw std::invalid_argument("One or both centerline objects not found");

        const ON_Curve* curveA = ON_Curve::Cast(objA->Geometry());
        const ON_Curve* curveB = ON_Curve::Cast(objB->Geometry());
        if (!curveA || !curveB)
            throw std::invalid_argument("Both centerline objects must be curves");

        const CandidateComputationResult candidateResult = ComputeRoadIntersectionCandidates(
            *curveA,
            *curveB,
            pDoc->AbsoluteTolerance(),
            toleranceOverride,
            overlapToleranceOverride,
            metadataA.get(),
            metadataB.get());

        const auto [selectedIndex, selectionMethod] = SelectCandidateIndex(body, candidateResult);
        const IntersectionCandidateInfo& selectedCandidate = candidateResult.candidates[selectedIndex];

        const nlohmann::json requiredSideSelections = BuildRequiredSideSelectionsJson(
            metadataA.get(), asymmetricSideA, metadataB.get(), asymmetricSideB);

        if (!metadataA && !metadataB)
        {
            nlohmann::json allCandidates = nlohmann::json::array();
            for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
                allCandidates.push_back(CandidateToJson(candidateResult.candidates[i], i));

            uint64_t tokenHash = Fnv1aInit();
            Fnv1aAppendString(tokenHash, UuidToString(centerlineA));
            Fnv1aAppendString(tokenHash, UuidToString(centerlineB));
            Fnv1aAppendString(tokenHash, "cand-" + std::to_string(selectedIndex));
            Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveA));
            Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveB));
            Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterA);
            Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterB);
            Fnv1aAppendDouble(tokenHash, selectedCandidate.stationA);
            Fnv1aAppendDouble(tokenHash, selectedCandidate.stationB);
            Fnv1aAppendDouble(tokenHash, candidateResult.tolerance);
            Fnv1aAppendDouble(tokenHash, candidateResult.overlapTolerance);
            for (double radius : filletRadii)
                Fnv1aAppendDouble(tokenHash, radius);

            nlohmann::json result;

            result["centerlineA"] = UuidToString(centerlineA);
            result["centerlineB"] = UuidToString(centerlineB);
            result["candidateCount"] = static_cast<int>(candidateResult.candidates.size());
            result["overlapCount"] = candidateResult.overlapCount;
            result["recommendedCandidateId"] =
                candidateResult.recommendedCandidateId.empty()
                    ? nlohmann::json(nullptr)
                    : nlohmann::json(candidateResult.recommendedCandidateId);
            result["selectionMethod"] = selectionMethod;
            result["selectedCandidate"] = CandidateToJson(selectedCandidate, selectedIndex);
            result["candidates"] = std::move(allCandidates);
            result["featureRules"] = nlohmann::json::array();
            result["orderedArms"] = BuildOrderedArmsJson(BuildOrderedArms(selectedCandidate));
            result["trimDecisions"] = nlohmann::json::array();
            result["cornerPairings"] = nlohmann::json::array();
            result["boundaryWalk"] = nlohmann::json::array();
            result["boundaryInvariants"] = nlohmann::json::array({
                MakeInvariantJson(
                    "profiles_required_for_topology",
                    false,
                    "No road profiles were supplied, so feature rules and commit-ready topology were not derived.")
            });
            result["provisionalBoundary2D"] = {
                { "validationMode", "profiles-required" },
                { "isClosed", false },
                { "isSelfIntersecting", false },
                { "area", 0.0 },
                { "centroid", nullptr },
                { "cornerPoints", nlohmann::json::array() }
            };
            result["analysisGeometry2D"] = {
                { "mode", "profiles-required" },
                { "boundarySegments", nlohmann::json::array() },
                { "curbReturnArcs", nlohmann::json::array() },
                { "boundarySegmentCount", 0 },
                { "curbReturnArcCount", 0 }
            };
            result["previewGeometry"] = BuildPreviewGeometryJson(selectedCandidate, filletRadii);
            result["analysisMode"] = "exact-native-curve-curve";
            result["analysisStage"] = "candidate-selection-no-profile-topology-skipped";
            result["readyForCommit"] = false;
            result["topologyReadyForGeometry"] = false;
            result["analysisToken"] = "ria-" + HashToHex(tokenHash);
            result["intersectionTolerance"] = RoundTo(candidateResult.tolerance, 6);
            result["overlapTolerance"] = RoundTo(candidateResult.overlapTolerance, 6);
            result["unresolvedConditions"].push_back(MakeUnresolvedCondition(
                "profiles_required_for_topology",
                "warning",
                "No road profiles were supplied, so feature topology and commit-ready boundary geometry were skipped."));
            return result;
        }

        if (!requiredSideSelections.empty())
        {
            uint64_t tokenHash = Fnv1aInit();
            Fnv1aAppendString(tokenHash, UuidToString(centerlineA));
            Fnv1aAppendString(tokenHash, UuidToString(centerlineB));
            Fnv1aAppendString(tokenHash, metadataA ? metadataA->name : std::string());
            Fnv1aAppendString(tokenHash, metadataB ? metadataB->name : std::string());
            Fnv1aAppendString(tokenHash, "cand-" + std::to_string(selectedIndex));
            Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveA));
            Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveB));
            Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterA);
            Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterB);
            Fnv1aAppendDouble(tokenHash, selectedCandidate.stationA);
            Fnv1aAppendDouble(tokenHash, selectedCandidate.stationB);
            Fnv1aAppendDouble(tokenHash, candidateResult.tolerance);
            Fnv1aAppendDouble(tokenHash, candidateResult.overlapTolerance);
            for (double radius : filletRadii)
                Fnv1aAppendDouble(tokenHash, radius);

            nlohmann::json allCandidates = nlohmann::json::array();
            for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
                allCandidates.push_back(CandidateToJson(candidateResult.candidates[i], i));

            nlohmann::json result;
            result["centerlineA"] = UuidToString(centerlineA);
            result["centerlineB"] = UuidToString(centerlineB);
            if (metadataA)
                result["profileA"] = RoadProfileMetadataToJson(*metadataA);
            if (metadataB)
                result["profileB"] = RoadProfileMetadataToJson(*metadataB);
            result["candidateCount"] = static_cast<int>(candidateResult.candidates.size());
            result["overlapCount"] = candidateResult.overlapCount;
            result["recommendedCandidateId"] =
                candidateResult.recommendedCandidateId.empty()
                    ? nlohmann::json(nullptr)
                    : nlohmann::json(candidateResult.recommendedCandidateId);
            result["selectionMethod"] = selectionMethod;
            result["selectedCandidate"] = CandidateToJson(selectedCandidate, selectedIndex);
            result["candidates"] = std::move(allCandidates);
            result["featureRules"] = nlohmann::json::array();
            result["orderedArms"] = BuildOrderedArmsJson(BuildOrderedArms(selectedCandidate));
            result["trimDecisions"] = nlohmann::json::array();
            result["cornerPairings"] = nlohmann::json::array();
            result["boundaryWalk"] = nlohmann::json::array();
            result["boundaryInvariants"] = nlohmann::json::array({
                MakeInvariantJson(
                    "asymmetric_side_selection_required",
                    false,
                    "At least one supplied road profile has unilateral features and still requires an explicit side selection.")
            });
            result["provisionalBoundary2D"] = {
                { "validationMode", "side-selection-required" },
                { "isClosed", false },
                { "isSelfIntersecting", nullptr },
                { "area", 0.0 },
                { "centroid", nullptr },
                { "cornerPoints", nlohmann::json::array() }
            };
            result["analysisGeometry2D"] = {
                { "mode", "side-selection-required" },
                { "boundarySegments", nlohmann::json::array() },
                { "curbReturnArcs", nlohmann::json::array() },
                { "boundarySegmentCount", 0 },
                { "curbReturnArcCount", 0 }
            };
            result["previewGeometry"] = BuildPreviewGeometryJson(selectedCandidate, filletRadii);
            result["analysisMode"] = "exact-native-curve-curve";
            result["analysisStage"] = "candidate-selection-profile-side-selection-required";
            result["readyForCommit"] = false;
            result["topologyReadyForGeometry"] = false;
            result["requiresSideSelection"] = true;
            result["requiredSideSelections"] = requiredSideSelections;
            result["selectionMessage"] = "Provide asymmetricSideA/asymmetricSideB for any road listed in requiredSideSelections before commit-ready topology can be computed.";
            result["analysisToken"] = "ria-" + HashToHex(tokenHash);
            result["intersectionTolerance"] = RoundTo(candidateResult.tolerance, 6);
            result["overlapTolerance"] = RoundTo(candidateResult.overlapTolerance, 6);
            result["unresolvedConditions"] = nlohmann::json::array();
            for (const auto& entry : requiredSideSelections)
            {
                result["unresolvedConditions"].push_back(MakeUnresolvedCondition(
                    "asymmetric_side_selection_required",
                    "warning",
                    entry.value("message", std::string())));
            }
            return result;
        }

        nlohmann::json unresolvedConditions = nlohmann::json::array();
        std::set<std::string> unresolvedConditionKeys;
        if (candidateResult.overlapCount > 0)
        {
            AppendUnresolvedCondition(
                unresolvedConditions,
                &unresolvedConditionKeys,
                "curve_overlap_detected",
                "warning",
                "One or more overlap events were detected during candidate analysis. Downstream trim logic should treat this case carefully.",
                "curve_overlap_detected");
        }
        if (selectedCandidate.requiredClearanceA > 0.0
            && selectedCandidate.endClearanceA + 1e-9 < selectedCandidate.requiredClearanceA)
        {
            AppendUnresolvedCondition(
                unresolvedConditions,
                &unresolvedConditionKeys,
                "insufficient_clearance_a",
                "warning",
                "Selected candidate does not have enough end clearance on road A for the supplied profile envelope.",
                "insufficient_clearance_a|A");
        }
        if (selectedCandidate.requiredClearanceB > 0.0
            && selectedCandidate.endClearanceB + 1e-9 < selectedCandidate.requiredClearanceB)
        {
            AppendUnresolvedCondition(
                unresolvedConditions,
                &unresolvedConditionKeys,
                "insufficient_clearance_b",
                "warning",
                "Selected candidate does not have enough end clearance on road B for the supplied profile envelope.",
                "insufficient_clearance_b|B");
        }

        std::vector<ResolvedFeature> resolvedFeatures = BuildResolvedFeatures(
            "A", metadataA.get(), asymmetricSideA, unresolvedConditions, &unresolvedConditionKeys);
        {
            std::vector<ResolvedFeature> bFeatures = BuildResolvedFeatures(
                "B", metadataB.get(), asymmetricSideB, unresolvedConditions, &unresolvedConditionKeys);
            resolvedFeatures.insert(resolvedFeatures.end(), bFeatures.begin(), bFeatures.end());
        }

        const std::vector<ArmInfo> orderedArms = BuildOrderedArms(selectedCandidate);
        nlohmann::json cornerPairings = nlohmann::json::array();
        nlohmann::json trimDecisions = nlohmann::json::array();
        std::vector<BoundaryCornerRecord> boundaryCornerRecords(orderedArms.size());
        for (size_t i = 0; i < orderedArms.size(); ++i)
        {
            const ArmInfo& incomingArm = orderedArms[i];
            const ArmInfo& outgoingArm = orderedArms[(i + 1) % orderedArms.size()];
            const ResolvedFeature* incomingCurb = FindCurbReturnFeature(resolvedFeatures, incomingArm.road, "right");
            const ResolvedFeature* outgoingCurb = FindCurbReturnFeature(resolvedFeatures, outgoingArm.road, "left");

            if (incomingCurb && outgoingCurb)
            {
                const double defaultRadius = RoundTo((std::min)(incomingCurb->offset, outgoingCurb->offset), 4);
                const double radius = (i < filletRadii.size()) ? filletRadii[i] : defaultRadius;

                nlohmann::json pairing;
                pairing["cornerOrder"] = static_cast<int>(i);
                pairing["incoming"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingCurb);
                pairing["outgoing"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingCurb);
                pairing["radius"] = radius;
                pairing["reason"] = "Adjacent-arm topology pairs the clockwise right side of the incoming arm to the left side of the outgoing arm.";
                boundaryCornerRecords[i].hasCornerPairing = true;
                boundaryCornerRecords[i].cornerPairing = pairing;
                cornerPairings.push_back(std::move(pairing));

                nlohmann::json trimIncoming;
                trimIncoming["decisionId"] = "trim-corner-" + std::to_string(i) + "-incoming";
                trimIncoming["cornerOrder"] = static_cast<int>(i);
                trimIncoming["key"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingCurb);
                trimIncoming["operation"] = "fillet_to_opposing_feature";
                trimIncoming["connectTo"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingCurb);
                trimIncoming["radius"] = radius;
                trimIncoming["reason"] = "Incoming curb is trimmed for the adjacent-arm curb return.";
                trimDecisions.push_back(std::move(trimIncoming));

                nlohmann::json trimOutgoing;
                trimOutgoing["decisionId"] = "trim-corner-" + std::to_string(i) + "-outgoing";
                trimOutgoing["cornerOrder"] = static_cast<int>(i);
                trimOutgoing["key"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingCurb);
                trimOutgoing["operation"] = "fillet_to_opposing_feature";
                trimOutgoing["connectTo"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingCurb);
                trimOutgoing["radius"] = radius;
                trimOutgoing["reason"] = "Outgoing curb is trimmed for the adjacent-arm curb return.";
                trimDecisions.push_back(std::move(trimOutgoing));
            }
            else
            {
                AppendUnresolvedCondition(
                    unresolvedConditions,
                    &unresolvedConditionKeys,
                    "missing_corner_curb",
                    "warning",
                    "A clockwise adjacent-arm corner is missing a present carriageway_edge on one side, so no curb return pairing was produced.",
                    "missing_corner_curb|" + std::to_string(i));
            }

            const BoundaryFeatureResolution incomingBoundary =
                ResolveBoundaryFeatureForSide(resolvedFeatures, incomingArm.road, "right");
            const BoundaryFeatureResolution outgoingBoundary =
                ResolveBoundaryFeatureForSide(resolvedFeatures, outgoingArm.road, "left");

            if (incomingBoundary.feature && !incomingBoundary.exactBoundaryRole)
            {
                AppendUnresolvedCondition(
                    unresolvedConditions,
                    &unresolvedConditionKeys,
                    "boundary_role_fallback",
                    "warning",
                    "Boundary resolution for road " + incomingArm.road + " right side fell back to "
                    + incomingBoundary.feature->type + " because no explicit outer boundary role is present on that side.",
                    "boundary_role_fallback|" + incomingArm.road + "|right");
            }
            if (outgoingBoundary.feature && !outgoingBoundary.exactBoundaryRole)
            {
                AppendUnresolvedCondition(
                    unresolvedConditions,
                    &unresolvedConditionKeys,
                    "boundary_role_fallback",
                    "warning",
                    "Boundary resolution for road " + outgoingArm.road + " left side fell back to "
                    + outgoingBoundary.feature->type + " because no explicit outer boundary role is present on that side.",
                    "boundary_role_fallback|" + outgoingArm.road + "|left");
            }

            if (incomingBoundary.feature && outgoingBoundary.feature)
            {
                nlohmann::json boundaryIncoming;
                boundaryIncoming["decisionId"] = "trim-boundary-" + std::to_string(i) + "-incoming";
                boundaryIncoming["cornerOrder"] = static_cast<int>(i);
                boundaryIncoming["key"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingBoundary.feature);
                boundaryIncoming["operation"] = incomingBoundary.exactBoundaryRole
                    ? "trim_for_boundary_walk"
                    : "trim_for_boundary_walk_fallback";
                boundaryIncoming["connectTo"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingBoundary.feature);
                boundaryIncoming["boundarySelectionMode"] = incomingBoundary.mode;
                boundaryIncoming["reason"] = incomingBoundary.reason;
                boundaryCornerRecords[i].hasBoundaryIncoming = true;
                boundaryCornerRecords[i].boundaryIncoming = boundaryIncoming;
                trimDecisions.push_back(std::move(boundaryIncoming));

                nlohmann::json boundaryOutgoing;
                boundaryOutgoing["decisionId"] = "trim-boundary-" + std::to_string(i) + "-outgoing";
                boundaryOutgoing["cornerOrder"] = static_cast<int>(i);
                boundaryOutgoing["key"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingBoundary.feature);
                boundaryOutgoing["operation"] = outgoingBoundary.exactBoundaryRole
                    ? "trim_for_boundary_walk"
                    : "trim_for_boundary_walk_fallback";
                boundaryOutgoing["connectTo"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingBoundary.feature);
                boundaryOutgoing["boundarySelectionMode"] = outgoingBoundary.mode;
                boundaryOutgoing["reason"] = outgoingBoundary.reason;
                boundaryCornerRecords[i].hasBoundaryOutgoing = true;
                boundaryCornerRecords[i].boundaryOutgoing = boundaryOutgoing;
                trimDecisions.push_back(std::move(boundaryOutgoing));
            }
            else
            {
                AppendUnresolvedCondition(
                    unresolvedConditions,
                    &unresolvedConditionKeys,
                    "missing_boundary_feature",
                    "warning",
                    "A clockwise adjacent-arm corner is missing a present boundary feature on one side, so no boundary trim decision was produced for that side.",
                    "missing_boundary_feature|" + std::to_string(i));
            }
        }

        nlohmann::json featureRules = BuildFeatureRulesJson(resolvedFeatures);
        nlohmann::json boundaryWalk = BuildBoundaryWalkJson(boundaryCornerRecords);

        std::vector<ON_2dPoint> provisionalBoundaryPoints;
        bool allCornerIntersectionsResolved = true;
        for (size_t i = 0; i < boundaryCornerRecords.size(); ++i)
        {
            const auto& record = boundaryCornerRecords[i];
            if (!record.hasBoundaryIncoming || !record.hasBoundaryOutgoing)
            {
                allCornerIntersectionsResolved = false;
                break;
            }

            BoundaryLine2D incomingLine;
            BoundaryLine2D outgoingLine;
            if (!TryBuildBoundaryLine2D(record.boundaryIncoming["key"], orderedArms, resolvedFeatures, selectedCandidate.point, incomingLine)
                || !TryBuildBoundaryLine2D(record.boundaryOutgoing["key"], orderedArms, resolvedFeatures, selectedCandidate.point, outgoingLine))
            {
                allCornerIntersectionsResolved = false;
                break;
            }

            ON_2dPoint cornerPoint;
            if (!TryIntersectLines2D(incomingLine, outgoingLine, cornerPoint))
            {
                allCornerIntersectionsResolved = false;
                break;
            }

            provisionalBoundaryPoints.push_back(cornerPoint);
        }

        const bool selfIntersectionChecked = allCornerIntersectionsResolved && provisionalBoundaryPoints.size() >= 3;
        const bool polygonSelfIntersecting = selfIntersectionChecked
            ? PolygonSelfIntersects(provisionalBoundaryPoints)
            : false;
        const double provisionalArea = selfIntersectionChecked
            ? std::fabs(PolygonSignedArea(provisionalBoundaryPoints))
            : 0.0;
        const ON_2dPoint provisionalCentroid = selfIntersectionChecked
            ? PolygonCentroid(provisionalBoundaryPoints)
            : ON_2dPoint::Origin;

        bool allCornersHavePairings = true;
        bool allCornersHaveIncomingBoundary = true;
        bool allCornersHaveOutgoingBoundary = true;
        for (const auto& record : boundaryCornerRecords)
        {
            allCornersHavePairings = allCornersHavePairings && record.hasCornerPairing;
            allCornersHaveIncomingBoundary = allCornersHaveIncomingBoundary && record.hasBoundaryIncoming;
            allCornersHaveOutgoingBoundary = allCornersHaveOutgoingBoundary && record.hasBoundaryOutgoing;
        }

        std::set<int> seenCornerOrders;
        bool duplicateCornerOrder = false;
        for (const auto& pairing : cornerPairings)
        {
            const int order = pairing.value("cornerOrder", -1);
            if (!seenCornerOrders.insert(order).second)
            {
                duplicateCornerOrder = true;
                break;
            }
        }

        const bool hasDeterministicBoundaryOrder = !boundaryWalk.empty();
        const bool hasNoOrphanBoundarySegments = allCornersHaveIncomingBoundary == allCornersHaveOutgoingBoundary;
        const bool isTopologicallyClosed =
            allCornersHavePairings && allCornersHaveIncomingBoundary && allCornersHaveOutgoingBoundary;

        nlohmann::json boundaryInvariants = nlohmann::json::array();
        boundaryInvariants.push_back(MakeInvariantJson(
            "single_selected_candidate",
            true,
            "Analyze response is scoped to exactly one selected candidate."));
        boundaryInvariants.push_back(MakeInvariantJson(
            "deterministic_ordered_boundary",
            hasDeterministicBoundaryOrder,
            hasDeterministicBoundaryOrder
                ? "Boundary walk segments are ordered clockwise by corner index."
                : "No boundary walk segments were assembled."));
        boundaryInvariants.push_back(MakeInvariantJson(
            "closed_loop_topology",
            isTopologicallyClosed,
            isTopologicallyClosed
                ? "Every corner contributes incoming boundary, curb return, and outgoing boundary segments."
                : "At least one corner is missing a boundary or curb-return segment, so the topology is not closed."));
        boundaryInvariants.push_back(MakeInvariantJson(
            "no_corner_paired_twice",
            !duplicateCornerOrder && seenCornerOrders.size() == boundaryCornerRecords.size(),
            (!duplicateCornerOrder && seenCornerOrders.size() == boundaryCornerRecords.size())
                ? "Each clockwise corner order is paired exactly once."
                : "One or more clockwise corners are missing or duplicated in corner pairings."));
        boundaryInvariants.push_back(MakeInvariantJson(
            "no_orphan_boundary_segments",
            hasNoOrphanBoundarySegments,
            hasNoOrphanBoundarySegments
                ? "Boundary trim decisions appear in balanced incoming/outgoing pairs."
                : "Boundary trim decisions are missing either incoming or outgoing coverage for at least one corner."));
        boundaryInvariants.push_back(MakeInvariantJson(
            "self_intersection_checked",
            selfIntersectionChecked,
            selfIntersectionChecked
                ? (polygonSelfIntersecting
                    ? "Local linearized boundary polygon self-intersects."
                    : "Local linearized boundary polygon does not self-intersect.")
                : "Local linearized corner intersections could not be resolved for geometric validation."));
        boundaryInvariants.push_back(MakeInvariantJson(
            "boundary_polygon_non_self_intersecting",
            selfIntersectionChecked && !polygonSelfIntersecting,
            selfIntersectionChecked
                ? (!polygonSelfIntersecting
                    ? "Local linearized boundary polygon is non-self-intersecting."
                    : "Local linearized boundary polygon self-intersects.")
                : "Boundary polygon could not be constructed for self-intersection validation."));

        const bool topologyReady =
            hasDeterministicBoundaryOrder
            && isTopologicallyClosed
            && !duplicateCornerOrder
            && hasNoOrphanBoundarySegments;

        nlohmann::json provisionalBoundary2D;
        provisionalBoundary2D["validationMode"] = "local-linearized-boundary-lines";
        provisionalBoundary2D["isClosed"] = selfIntersectionChecked;
        provisionalBoundary2D["isSelfIntersecting"] = selfIntersectionChecked ? polygonSelfIntersecting : nlohmann::json(nullptr);
        provisionalBoundary2D["area"] = RoundTo(provisionalArea, 4);
        provisionalBoundary2D["centroid"] = selfIntersectionChecked
            ? nlohmann::json::array({ RoundTo(provisionalCentroid.x, 4), RoundTo(provisionalCentroid.y, 4), 0.0 })
            : nlohmann::json(nullptr);
        nlohmann::json provisionalPointsJson = nlohmann::json::array();
        for (const auto& point : provisionalBoundaryPoints)
            provisionalPointsJson.push_back(nlohmann::json::array({ RoundTo(point.x, 4), RoundTo(point.y, 4), 0.0 }));
        provisionalBoundary2D["cornerPoints"] = std::move(provisionalPointsJson);

        nlohmann::json analysisGeometry2D;
        analysisGeometry2D["mode"] = "read_only_world_xy";
        nlohmann::json boundarySegments2D = nlohmann::json::array();
        if (selfIntersectionChecked && provisionalBoundaryPoints.size() >= 2)
        {
            for (size_t i = 0; i < provisionalBoundaryPoints.size(); ++i)
            {
                const size_t next = (i + 1) % provisionalBoundaryPoints.size();
                nlohmann::json segment;
                segment["segmentType"] = "line";
                segment["cornerOrder"] = static_cast<int>(i);
                segment["startPoint"] = Point2dAsPoint3Json(provisionalBoundaryPoints[i]);
                segment["endPoint"] = Point2dAsPoint3Json(provisionalBoundaryPoints[next]);
                boundarySegments2D.push_back(std::move(segment));
            }
        }
        analysisGeometry2D["boundarySegments"] = std::move(boundarySegments2D);

        nlohmann::json curbReturnArcs2D = nlohmann::json::array();
        for (const auto& pairing : cornerPairings)
        {
            nlohmann::json arc;
            if (TryBuildCurbReturnArc2D(pairing, orderedArms, resolvedFeatures, selectedCandidate.point, arc))
            {
                curbReturnArcs2D.push_back(std::move(arc));
            }
        }
        analysisGeometry2D["curbReturnArcs"] = std::move(curbReturnArcs2D);
        analysisGeometry2D["boundarySegmentCount"] = analysisGeometry2D["boundarySegments"].size();
        analysisGeometry2D["curbReturnArcCount"] = analysisGeometry2D["curbReturnArcs"].size();

        nlohmann::json allCandidates = nlohmann::json::array();
        for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
            allCandidates.push_back(CandidateToJson(candidateResult.candidates[i], i));

        uint64_t tokenHash = Fnv1aInit();
        Fnv1aAppendString(tokenHash, UuidToString(centerlineA));
        Fnv1aAppendString(tokenHash, UuidToString(centerlineB));
        Fnv1aAppendString(tokenHash, metadataA ? metadataA->name : std::string());
        Fnv1aAppendString(tokenHash, metadataB ? metadataB->name : std::string());
        Fnv1aAppendString(tokenHash, asymmetricSideA);
        Fnv1aAppendString(tokenHash, asymmetricSideB);
        Fnv1aAppendString(tokenHash, "cand-" + std::to_string(selectedIndex));
        Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveA));
        Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveB));
        Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterA);
        Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterB);
        Fnv1aAppendDouble(tokenHash, selectedCandidate.stationA);
        Fnv1aAppendDouble(tokenHash, selectedCandidate.stationB);
        Fnv1aAppendDouble(tokenHash, candidateResult.tolerance);
        Fnv1aAppendDouble(tokenHash, candidateResult.overlapTolerance);
        for (double radius : filletRadii)
            Fnv1aAppendDouble(tokenHash, radius);

        nlohmann::json result;
        result["centerlineA"] = UuidToString(centerlineA);
        result["centerlineB"] = UuidToString(centerlineB);
        if (metadataA)
            result["profileA"] = RoadProfileMetadataToJson(*metadataA);
        if (metadataB)
            result["profileB"] = RoadProfileMetadataToJson(*metadataB);
        result["candidateCount"] = static_cast<int>(candidateResult.candidates.size());
        result["overlapCount"] = candidateResult.overlapCount;
        result["recommendedCandidateId"] =
            candidateResult.recommendedCandidateId.empty()
                ? nlohmann::json(nullptr)
                : nlohmann::json(candidateResult.recommendedCandidateId);
        result["selectionMethod"] = selectionMethod;
        result["selectedCandidate"] = CandidateToJson(selectedCandidate, selectedIndex);
        result["candidates"] = std::move(allCandidates);
        result["featureRules"] = std::move(featureRules);
        result["orderedArms"] = BuildOrderedArmsJson(orderedArms);
        result["trimDecisions"] = std::move(trimDecisions);
        result["cornerPairings"] = std::move(cornerPairings);
        result["boundaryWalk"] = std::move(boundaryWalk);
        result["boundaryInvariants"] = std::move(boundaryInvariants);
        result["provisionalBoundary2D"] = std::move(provisionalBoundary2D);
        result["analysisGeometry2D"] = std::move(analysisGeometry2D);
        result["previewGeometry"] = BuildPreviewGeometryJson(selectedCandidate, filletRadii);
        result["unresolvedConditions"] = std::move(unresolvedConditions);
        result["analysisStage"] = "candidate-selection-feature-rules-corner-topology-boundary-walk-and-analysis-geometry-2d";
        result["readyForCommit"] =
            topologyReady
            && selfIntersectionChecked
            && !polygonSelfIntersecting
            && result["analysisGeometry2D"]["boundarySegmentCount"].get<size_t>() > 0
            && result["analysisGeometry2D"]["curbReturnArcCount"].get<size_t>() == result["cornerPairings"].size();
        result["topologyReadyForGeometry"] = topologyReady;
        result["analysisToken"] = "ria-" + HashToHex(tokenHash);
        result["analysisMode"] = "exact-native-curve-curve";
        result["intersectionTolerance"] = RoundTo(candidateResult.tolerance, 6);
        result["overlapTolerance"] = RoundTo(candidateResult.overlapTolerance, 6);
        if (!filletRadii.empty())
            result["filletRadii"] = filletRadii;
        if (!asymmetricSideA.empty())
            result["asymmetricSideA"] = asymmetricSideA;
        if (!asymmetricSideB.empty())
            result["asymmetricSideB"] = asymmetricSideB;
        return result;
    });

    try
    {
        nlohmann::json result = future.get();
        CacheIntersectionAnalyzeRequest(result.value("analysisToken", std::string()), docSn, body);
        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

static nlohmann::json ComputeRoadIntersectionAnalyzeForCommit(
    unsigned int docSn,
    const nlohmann::json& body,
    ON_UUID centerlineA,
    ON_UUID centerlineB,
    const std::string& asymmetricSideA,
    const std::string& asymmetricSideB,
    double toleranceOverride,
    double overlapToleranceOverride,
    const std::vector<double>& filletRadii,
    const RoadProfileMetadata* metadataA,
    const RoadProfileMetadata* metadataB)
{
    CRhinoDoc* pDoc = ResolveDoc(docSn);

    const CRhinoObject* objA = pDoc->LookupObject(centerlineA);
    const CRhinoObject* objB = pDoc->LookupObject(centerlineB);
    if (!objA || !objB)
        throw std::invalid_argument("One or both centerline objects not found");

    const ON_Curve* curveA = ON_Curve::Cast(objA->Geometry());
    const ON_Curve* curveB = ON_Curve::Cast(objB->Geometry());
    if (!curveA || !curveB)
        throw std::invalid_argument("Both centerline objects must be curves");

    const CandidateComputationResult candidateResult = ComputeRoadIntersectionCandidates(
        *curveA,
        *curveB,
        pDoc->AbsoluteTolerance(),
        toleranceOverride,
        overlapToleranceOverride,
        metadataA,
        metadataB);

    const auto [selectedIndex, selectionMethod] = SelectCandidateIndex(body, candidateResult);
    const IntersectionCandidateInfo& selectedCandidate = candidateResult.candidates[selectedIndex];

    const nlohmann::json requiredSideSelections = BuildRequiredSideSelectionsJson(
        metadataA, asymmetricSideA, metadataB, asymmetricSideB);

    if (!requiredSideSelections.empty())
    {
        uint64_t tokenHash = Fnv1aInit();
        Fnv1aAppendString(tokenHash, UuidToString(centerlineA));
        Fnv1aAppendString(tokenHash, UuidToString(centerlineB));
        Fnv1aAppendString(tokenHash, metadataA ? metadataA->name : std::string());
        Fnv1aAppendString(tokenHash, metadataB ? metadataB->name : std::string());
        Fnv1aAppendString(tokenHash, "cand-" + std::to_string(selectedIndex));
        Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveA));
        Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveB));
        Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterA);
        Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterB);
        Fnv1aAppendDouble(tokenHash, selectedCandidate.stationA);
        Fnv1aAppendDouble(tokenHash, selectedCandidate.stationB);
        Fnv1aAppendDouble(tokenHash, candidateResult.tolerance);
        Fnv1aAppendDouble(tokenHash, candidateResult.overlapTolerance);
        for (double radius : filletRadii)
            Fnv1aAppendDouble(tokenHash, radius);

        nlohmann::json allCandidates = nlohmann::json::array();
        for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
            allCandidates.push_back(CandidateToJson(candidateResult.candidates[i], i));

        nlohmann::json result;
        result["centerlineA"] = UuidToString(centerlineA);
        result["centerlineB"] = UuidToString(centerlineB);
        if (metadataA)
            result["profileA"] = RoadProfileMetadataToJson(*metadataA);
        if (metadataB)
            result["profileB"] = RoadProfileMetadataToJson(*metadataB);
        result["selectedCandidate"] = CandidateToJson(selectedCandidate, selectedIndex);
        result["selectionMethod"] = selectionMethod;
        result["candidateCount"] = static_cast<int>(candidateResult.candidates.size());
        result["overlapCount"] = candidateResult.overlapCount;
        result["recommendedCandidateId"] =
            candidateResult.recommendedCandidateId.empty()
                ? nlohmann::json(nullptr)
                : nlohmann::json(candidateResult.recommendedCandidateId);
        result["candidates"] = std::move(allCandidates);
        result["analysisToken"] = "ria-" + HashToHex(tokenHash);
        result["analysisStage"] = "candidate-selection-profile-side-selection-required";
        result["topologyReadyForGeometry"] = false;
        result["readyForCommit"] = false;
        result["requiresSideSelection"] = true;
        result["requiredSideSelections"] = requiredSideSelections;
        result["selectionMessage"] = "Provide asymmetricSideA/asymmetricSideB for any road listed in requiredSideSelections before commit-ready topology can be computed.";
        result["featureRules"] = nlohmann::json::array();
        result["orderedArms"] = BuildOrderedArmsJson(BuildOrderedArms(selectedCandidate));
        result["trimDecisions"] = nlohmann::json::array();
        result["cornerPairings"] = nlohmann::json::array();
        result["boundaryWalk"] = nlohmann::json::array();
        result["provisionalBoundary2D"] = {
            { "validationMode", "side-selection-required" },
            { "isClosed", false },
            { "isSelfIntersecting", nullptr },
            { "area", 0.0 },
            { "centroid", nullptr },
            { "cornerPoints", nlohmann::json::array() }
        };
        result["analysisGeometry2D"] = {
            { "mode", "side-selection-required" },
            { "boundarySegments", nlohmann::json::array() },
            { "curbReturnArcs", nlohmann::json::array() },
            { "boundarySegmentCount", 0 },
            { "curbReturnArcCount", 0 }
        };
        result["previewGeometry"] = BuildPreviewGeometryJson(selectedCandidate, filletRadii);
        result["intersectionTolerance"] = RoundTo(candidateResult.tolerance, 6);
        result["overlapTolerance"] = RoundTo(candidateResult.overlapTolerance, 6);
        result["unresolvedConditions"] = nlohmann::json::array();
        for (const auto& entry : requiredSideSelections)
        {
            result["unresolvedConditions"].push_back(MakeUnresolvedCondition(
                "asymmetric_side_selection_required",
                "warning",
                entry.value("message", std::string())));
        }
        if (!asymmetricSideA.empty())
            result["asymmetricSideA"] = asymmetricSideA;
        if (!asymmetricSideB.empty())
            result["asymmetricSideB"] = asymmetricSideB;
        return result;
    }

    nlohmann::json unresolvedConditions = nlohmann::json::array();
    std::set<std::string> unresolvedConditionKeys;
    if (candidateResult.overlapCount > 0)
    {
        AppendUnresolvedCondition(
            unresolvedConditions,
            &unresolvedConditionKeys,
            "curve_overlap_detected",
            "warning",
            "One or more overlap events were detected during candidate analysis. Downstream trim logic should treat this case carefully.",
            "curve_overlap_detected");
    }

    if (metadataA && selectedCandidate.endClearanceA + 1e-9 < selectedCandidate.requiredClearanceA)
    {
        AppendUnresolvedCondition(
            unresolvedConditions,
            &unresolvedConditionKeys,
            "insufficient_end_clearance_a",
            "warning",
            "Selected candidate does not have enough end clearance on road A for the supplied profile envelope.",
            "insufficient_end_clearance_a|A");
    }
    if (metadataB && selectedCandidate.endClearanceB + 1e-9 < selectedCandidate.requiredClearanceB)
    {
        AppendUnresolvedCondition(
            unresolvedConditions,
            &unresolvedConditionKeys,
            "insufficient_end_clearance_b",
            "warning",
            "Selected candidate does not have enough end clearance on road B for the supplied profile envelope.",
            "insufficient_end_clearance_b|B");
    }

    std::vector<ResolvedFeature> resolvedFeatures = BuildResolvedFeatures(
        "A", metadataA, asymmetricSideA, unresolvedConditions, &unresolvedConditionKeys);
    {
        std::vector<ResolvedFeature> bFeatures = BuildResolvedFeatures(
            "B", metadataB, asymmetricSideB, unresolvedConditions, &unresolvedConditionKeys);
        resolvedFeatures.insert(resolvedFeatures.end(), bFeatures.begin(), bFeatures.end());
    }

    const std::vector<ArmInfo> orderedArms = BuildOrderedArms(selectedCandidate);
    nlohmann::json cornerPairings = nlohmann::json::array();
    nlohmann::json trimDecisions = nlohmann::json::array();
    std::vector<BoundaryCornerRecord> boundaryCornerRecords(orderedArms.size());
    for (size_t i = 0; i < orderedArms.size(); ++i)
    {
        const ArmInfo& incomingArm = orderedArms[i];
        const ArmInfo& outgoingArm = orderedArms[(i + 1) % orderedArms.size()];
        const ResolvedFeature* incomingCurb = FindCurbReturnFeature(resolvedFeatures, incomingArm.road, "right");
        const ResolvedFeature* outgoingCurb = FindCurbReturnFeature(resolvedFeatures, outgoingArm.road, "left");

        if (incomingCurb && outgoingCurb)
        {
            const double defaultRadius = RoundTo((std::min)(incomingCurb->offset, outgoingCurb->offset), 4);
            const double radius = (i < filletRadii.size()) ? filletRadii[i] : defaultRadius;

            nlohmann::json pairing;
            pairing["cornerOrder"] = static_cast<int>(i);
            pairing["incoming"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingCurb);
            pairing["outgoing"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingCurb);
            pairing["radius"] = radius;
            pairing["reason"] = "Adjacent-arm topology pairs the clockwise right side of the incoming arm to the left side of the outgoing arm.";
            boundaryCornerRecords[i].hasCornerPairing = true;
            boundaryCornerRecords[i].cornerPairing = pairing;
            cornerPairings.push_back(std::move(pairing));

            nlohmann::json trimIncoming;
            trimIncoming["decisionId"] = "trim-corner-" + std::to_string(i) + "-incoming";
            trimIncoming["cornerOrder"] = static_cast<int>(i);
            trimIncoming["key"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingCurb);
            trimIncoming["operation"] = "fillet_to_opposing_feature";
            trimIncoming["connectTo"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingCurb);
            trimIncoming["radius"] = radius;
            trimIncoming["reason"] = "Incoming curb is trimmed for the adjacent-arm curb return.";
            trimDecisions.push_back(std::move(trimIncoming));

            nlohmann::json trimOutgoing;
            trimOutgoing["decisionId"] = "trim-corner-" + std::to_string(i) + "-outgoing";
            trimOutgoing["cornerOrder"] = static_cast<int>(i);
            trimOutgoing["key"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingCurb);
            trimOutgoing["operation"] = "fillet_to_opposing_feature";
            trimOutgoing["connectTo"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingCurb);
            trimOutgoing["radius"] = radius;
            trimOutgoing["reason"] = "Outgoing curb is trimmed for the adjacent-arm curb return.";
            trimDecisions.push_back(std::move(trimOutgoing));
        }

        const BoundaryFeatureResolution incomingBoundary =
            ResolveBoundaryFeatureForSide(resolvedFeatures, incomingArm.road, "right");
        const BoundaryFeatureResolution outgoingBoundary =
            ResolveBoundaryFeatureForSide(resolvedFeatures, outgoingArm.road, "left");

        if (incomingBoundary.feature && !incomingBoundary.exactBoundaryRole)
        {
            AppendUnresolvedCondition(
                unresolvedConditions,
                &unresolvedConditionKeys,
                "boundary_role_fallback",
                "warning",
                "Boundary resolution for road " + incomingArm.road + " right side fell back to "
                + incomingBoundary.feature->type + " because no explicit outer boundary role is present on that side.",
                "boundary_role_fallback|" + incomingArm.road + "|right");
        }
        if (outgoingBoundary.feature && !outgoingBoundary.exactBoundaryRole)
        {
            AppendUnresolvedCondition(
                unresolvedConditions,
                &unresolvedConditionKeys,
                "boundary_role_fallback",
                "warning",
                "Boundary resolution for road " + outgoingArm.road + " left side fell back to "
                + outgoingBoundary.feature->type + " because no explicit outer boundary role is present on that side.",
                "boundary_role_fallback|" + outgoingArm.road + "|left");
        }

        if (incomingBoundary.feature && outgoingBoundary.feature)
        {
            nlohmann::json boundaryIncoming;
            boundaryIncoming["decisionId"] = "trim-boundary-" + std::to_string(i) + "-incoming";
            boundaryIncoming["cornerOrder"] = static_cast<int>(i);
            boundaryIncoming["key"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingBoundary.feature);
            boundaryIncoming["operation"] = incomingBoundary.exactBoundaryRole
                ? "trim_for_boundary_walk"
                : "trim_for_boundary_walk_fallback";
            boundaryIncoming["connectTo"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingBoundary.feature);
            boundaryIncoming["boundarySelectionMode"] = incomingBoundary.mode;
            boundaryIncoming["reason"] = incomingBoundary.reason;
            boundaryCornerRecords[i].hasBoundaryIncoming = true;
            boundaryCornerRecords[i].boundaryIncoming = boundaryIncoming;
            trimDecisions.push_back(std::move(boundaryIncoming));

            nlohmann::json boundaryOutgoing;
            boundaryOutgoing["decisionId"] = "trim-boundary-" + std::to_string(i) + "-outgoing";
            boundaryOutgoing["cornerOrder"] = static_cast<int>(i);
            boundaryOutgoing["key"] = MakeArmFeatureKeyJson(outgoingArm.armId, *outgoingBoundary.feature);
            boundaryOutgoing["operation"] = outgoingBoundary.exactBoundaryRole
                ? "trim_for_boundary_walk"
                : "trim_for_boundary_walk_fallback";
            boundaryOutgoing["connectTo"] = MakeArmFeatureKeyJson(incomingArm.armId, *incomingBoundary.feature);
            boundaryOutgoing["boundarySelectionMode"] = outgoingBoundary.mode;
            boundaryOutgoing["reason"] = outgoingBoundary.reason;
            boundaryCornerRecords[i].hasBoundaryOutgoing = true;
            boundaryCornerRecords[i].boundaryOutgoing = boundaryOutgoing;
            trimDecisions.push_back(std::move(boundaryOutgoing));
        }
        else
        {
            AppendUnresolvedCondition(
                unresolvedConditions,
                &unresolvedConditionKeys,
                "missing_boundary_feature",
                "warning",
                "A clockwise adjacent-arm corner is missing a present boundary feature on one side, so no boundary trim decision was produced for that side.",
                "missing_boundary_feature|" + std::to_string(i));
        }
    }

    std::vector<ON_2dPoint> provisionalBoundaryPoints;
    bool allCornerIntersectionsResolved = true;
    for (size_t i = 0; i < boundaryCornerRecords.size(); ++i)
    {
        const auto& record = boundaryCornerRecords[i];
        if (!record.hasBoundaryIncoming || !record.hasBoundaryOutgoing)
        {
            allCornerIntersectionsResolved = false;
            break;
        }

        BoundaryLine2D incomingLine;
        BoundaryLine2D outgoingLine;
        if (!TryBuildBoundaryLine2D(record.boundaryIncoming["key"], orderedArms, resolvedFeatures, selectedCandidate.point, incomingLine)
            || !TryBuildBoundaryLine2D(record.boundaryOutgoing["key"], orderedArms, resolvedFeatures, selectedCandidate.point, outgoingLine))
        {
            allCornerIntersectionsResolved = false;
            break;
        }

        ON_2dPoint cornerPoint;
        if (!TryIntersectLines2D(incomingLine, outgoingLine, cornerPoint))
        {
            allCornerIntersectionsResolved = false;
            break;
        }

        provisionalBoundaryPoints.push_back(cornerPoint);
    }

    const bool selfIntersectionChecked = allCornerIntersectionsResolved && provisionalBoundaryPoints.size() >= 3;
    const bool polygonSelfIntersecting = selfIntersectionChecked
        ? PolygonSelfIntersects(provisionalBoundaryPoints)
        : false;
    const double provisionalArea = selfIntersectionChecked
        ? std::fabs(PolygonSignedArea(provisionalBoundaryPoints))
        : 0.0;
    const ON_2dPoint provisionalCentroid = selfIntersectionChecked
        ? PolygonCentroid(provisionalBoundaryPoints)
        : ON_2dPoint::Origin;

    nlohmann::json provisionalBoundary2D;
    provisionalBoundary2D["validationMode"] = "local-linearized-boundary-lines";
    provisionalBoundary2D["isClosed"] = selfIntersectionChecked;
    provisionalBoundary2D["isSelfIntersecting"] = selfIntersectionChecked ? polygonSelfIntersecting : nlohmann::json(nullptr);
    provisionalBoundary2D["area"] = RoundTo(provisionalArea, 4);
    provisionalBoundary2D["centroid"] = selfIntersectionChecked
        ? nlohmann::json::array({ RoundTo(provisionalCentroid.x, 4), RoundTo(provisionalCentroid.y, 4), 0.0 })
        : nlohmann::json(nullptr);
    nlohmann::json provisionalPointsJson = nlohmann::json::array();
    for (const auto& point : provisionalBoundaryPoints)
        provisionalPointsJson.push_back(nlohmann::json::array({ RoundTo(point.x, 4), RoundTo(point.y, 4), 0.0 }));
    provisionalBoundary2D["cornerPoints"] = std::move(provisionalPointsJson);

    nlohmann::json analysisGeometry2D;
    analysisGeometry2D["mode"] = "read_only_world_xy";
    nlohmann::json boundarySegments2D = nlohmann::json::array();
    if (selfIntersectionChecked && provisionalBoundaryPoints.size() >= 2)
    {
        for (size_t i = 0; i < provisionalBoundaryPoints.size(); ++i)
        {
            const size_t next = (i + 1) % provisionalBoundaryPoints.size();
            nlohmann::json segment;
            segment["segmentType"] = "line";
            segment["cornerOrder"] = static_cast<int>(i);
            segment["startPoint"] = Point2dAsPoint3Json(provisionalBoundaryPoints[i]);
            segment["endPoint"] = Point2dAsPoint3Json(provisionalBoundaryPoints[next]);
            boundarySegments2D.push_back(std::move(segment));
        }
    }
    analysisGeometry2D["boundarySegments"] = std::move(boundarySegments2D);

    nlohmann::json curbReturnArcs2D = nlohmann::json::array();
    for (const auto& pairing : cornerPairings)
    {
        nlohmann::json arc;
        if (TryBuildCurbReturnArc2D(pairing, orderedArms, resolvedFeatures, selectedCandidate.point, arc))
            curbReturnArcs2D.push_back(std::move(arc));
    }
    analysisGeometry2D["curbReturnArcs"] = std::move(curbReturnArcs2D);
    analysisGeometry2D["boundarySegmentCount"] = analysisGeometry2D["boundarySegments"].size();
    analysisGeometry2D["curbReturnArcCount"] = analysisGeometry2D["curbReturnArcs"].size();

    bool allCornersHavePairings = true;
    bool allCornersHaveIncomingBoundary = true;
    bool allCornersHaveOutgoingBoundary = true;
    for (const auto& record : boundaryCornerRecords)
    {
        allCornersHavePairings = allCornersHavePairings && record.hasCornerPairing;
        allCornersHaveIncomingBoundary = allCornersHaveIncomingBoundary && record.hasBoundaryIncoming;
        allCornersHaveOutgoingBoundary = allCornersHaveOutgoingBoundary && record.hasBoundaryOutgoing;
    }

    std::set<int> seenCornerOrders;
    bool duplicateCornerOrder = false;
    for (const auto& pairing : cornerPairings)
    {
        const int order = pairing.value("cornerOrder", -1);
        if (!seenCornerOrders.insert(order).second)
        {
            duplicateCornerOrder = true;
            break;
        }
    }

    const bool hasDeterministicBoundaryOrder = analysisGeometry2D["boundarySegmentCount"].get<size_t>() > 0;
    const bool hasNoOrphanBoundarySegments = allCornersHaveIncomingBoundary == allCornersHaveOutgoingBoundary;
    const bool topologyReady =
        hasDeterministicBoundaryOrder
        && allCornersHavePairings
        && allCornersHaveIncomingBoundary
        && allCornersHaveOutgoingBoundary
        && !duplicateCornerOrder
        && hasNoOrphanBoundarySegments;

    uint64_t tokenHash = Fnv1aInit();
    Fnv1aAppendString(tokenHash, UuidToString(centerlineA));
    Fnv1aAppendString(tokenHash, UuidToString(centerlineB));
    Fnv1aAppendString(tokenHash, metadataA ? metadataA->name : std::string());
    Fnv1aAppendString(tokenHash, metadataB ? metadataB->name : std::string());
    Fnv1aAppendString(tokenHash, asymmetricSideA);
    Fnv1aAppendString(tokenHash, asymmetricSideB);
    Fnv1aAppendString(tokenHash, "cand-" + std::to_string(selectedIndex));
    Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveA));
    Fnv1aAppendString(tokenHash, BuildCurveSignature(*curveB));
    Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterA);
    Fnv1aAppendDouble(tokenHash, selectedCandidate.parameterB);
    Fnv1aAppendDouble(tokenHash, selectedCandidate.stationA);
    Fnv1aAppendDouble(tokenHash, selectedCandidate.stationB);
    Fnv1aAppendDouble(tokenHash, candidateResult.tolerance);
    Fnv1aAppendDouble(tokenHash, candidateResult.overlapTolerance);
    for (double radius : filletRadii)
        Fnv1aAppendDouble(tokenHash, radius);

    nlohmann::json featureRules = BuildFeatureRulesJson(resolvedFeatures);
    nlohmann::json boundaryWalk = BuildBoundaryWalkJson(boundaryCornerRecords);

    nlohmann::json result;
    result["centerlineA"] = UuidToString(centerlineA);
    result["centerlineB"] = UuidToString(centerlineB);
    if (metadataA)
        result["profileA"] = RoadProfileMetadataToJson(*metadataA);
    if (metadataB)
        result["profileB"] = RoadProfileMetadataToJson(*metadataB);
    result["selectedCandidate"] = CandidateToJson(selectedCandidate, selectedIndex);
    result["selectionMethod"] = selectionMethod;
    result["analysisToken"] = "ria-" + HashToHex(tokenHash);
    result["analysisStage"] = "candidate-selection-feature-rules-corner-topology-boundary-walk-and-analysis-geometry-2d";
    result["topologyReadyForGeometry"] = topologyReady;
    result["readyForCommit"] =
        topologyReady
        && selfIntersectionChecked
        && !polygonSelfIntersecting
        && analysisGeometry2D["boundarySegmentCount"].get<size_t>() > 0
        && analysisGeometry2D["curbReturnArcCount"].get<size_t>() == cornerPairings.size();
    result["featureRules"] = std::move(featureRules);
    result["orderedArms"] = BuildOrderedArmsJson(orderedArms);
    result["trimDecisions"] = std::move(trimDecisions);
    result["cornerPairings"] = std::move(cornerPairings);
    result["boundaryWalk"] = std::move(boundaryWalk);
    result["provisionalBoundary2D"] = std::move(provisionalBoundary2D);
    result["analysisGeometry2D"] = std::move(analysisGeometry2D);
    result["previewGeometry"] = BuildPreviewGeometryJson(selectedCandidate, filletRadii);
    result["unresolvedConditions"] = std::move(unresolvedConditions);
    result["intersectionTolerance"] = RoundTo(candidateResult.tolerance, 6);
    result["overlapTolerance"] = RoundTo(candidateResult.overlapTolerance, 6);
    if (!filletRadii.empty())
        result["filletRadii"] = filletRadii;
    if (!asymmetricSideA.empty())
        result["asymmetricSideA"] = asymmetricSideA;
    if (!asymmetricSideB.empty())
        result["asymmetricSideB"] = asymmetricSideB;
    return result;
}

static ON_3dPoint JsonValueToPoint3d(const nlohmann::json& value)
{
    if (value.is_array())
    {
        if (value.size() < 2)
            throw std::invalid_argument("Point array must have at least 2 elements");
        return ON_3dPoint(
            value[0].get<double>(),
            value[1].get<double>(),
            value.size() >= 3 ? value[2].get<double>() : 0.0);
    }

    if (value.is_object())
        return ON_3dPoint(value.value("x", 0.0), value.value("y", 0.0), value.value("z", 0.0));

    throw std::invalid_argument("Point value must be an array or object");
}

static std::string GetLayerFullPathUtf8(CRhinoDoc* pDoc, int layerIndex)
{
    ON_wString fullPath;
    pDoc->m_layer_table.GetLayerPathName(layerIndex, fullPath);
    return WideToUtf8(fullPath);
}

static std::vector<std::string> SplitLayerPath(const std::string& fullPath)
{
    std::vector<std::string> parts;
    size_t start = 0;
    while (start < fullPath.size())
    {
        const size_t sep = fullPath.find("::", start);
        std::string part = sep == std::string::npos
            ? fullPath.substr(start)
            : fullPath.substr(start, sep - start);
        if (!part.empty())
            parts.push_back(part);
        if (sep == std::string::npos)
            break;
        start = sep + 2;
    }
    return parts;
}

static int EnsureLayerPath(CRhinoDoc* pDoc, const std::string& fullPath)
{
    if (fullPath.empty())
        throw std::invalid_argument("targetLayerRoot must not be empty");

    if (const int existing = FindLayerIndex(pDoc, fullPath); existing >= 0)
        return existing;

    const std::vector<std::string> parts = SplitLayerPath(fullPath);
    int parentIndex = -1;
    std::string currentPath;
    for (const auto& part : parts)
    {
        currentPath = currentPath.empty() ? part : currentPath + "::" + part;
        int currentIndex = FindLayerIndex(pDoc, currentPath);
        if (currentIndex >= 0)
        {
            parentIndex = currentIndex;
            continue;
        }

        ON_Layer layer;
        layer.SetName(Utf8ToWide(part));
        if (parentIndex >= 0)
            layer.SetParentLayerId(pDoc->m_layer_table[parentIndex].Id());

        currentIndex = pDoc->m_layer_table.AddLayer(layer);
        if (currentIndex < 0)
            throw std::runtime_error("Failed to create layer path: " + currentPath);

        parentIndex = currentIndex;
    }

    if (parentIndex < 0)
        throw std::runtime_error("Failed to resolve layer path: " + fullPath);
    return parentIndex;
}

static ON_3dmObjectAttributes MakeIntersectionArtifactAttributes(
    int layerIndex,
    const std::string& name,
    const std::string& analysisToken,
    const std::string& artifactRole,
    const std::string& artifactKind = "analysis_guides_2d")
{
    ON_3dmObjectAttributes attrs;
    attrs.m_layer_index = layerIndex;
    attrs.m_name = Utf8ToWide(name);
    attrs.SetUserString(L"rook_intersection_analysis_token", Utf8ToWide(analysisToken));
    attrs.SetUserString(L"rook_intersection_artifact_role", Utf8ToWide(artifactRole));
    attrs.SetUserString(L"rook_intersection_artifact_kind", Utf8ToWide(artifactKind));
    return attrs;
}

static bool TryBuildCommittedArc(const nlohmann::json& arcJson, ON_Arc& arcOut, double& lengthOut)
{
    const ON_3dPoint center = JsonValueToPoint3d(arcJson.at("center"));
    const ON_3dPoint startPoint = JsonValueToPoint3d(arcJson.at("startPoint"));
    const ON_3dPoint endPoint = JsonValueToPoint3d(arcJson.at("endPoint"));
    const double radius = arcJson.at("radius").get<double>();
    if (!(radius > 0.0) || !std::isfinite(radius))
        return false;

    const double startAngle = std::atan2(startPoint.y - center.y, startPoint.x - center.x);
    const double endAngle = std::atan2(endPoint.y - center.y, endPoint.x - center.x);
    double sweep = NormalizeAngleRadians(endAngle - startAngle);
    if (sweep > ON_PI)
        sweep -= 2.0 * ON_PI;

    const double midAngle = startAngle + 0.5 * sweep;
    const ON_3dPoint midPoint(
        center.x + radius * std::cos(midAngle),
        center.y + radius * std::sin(midAngle),
        center.z);

    ON_Arc arc(startPoint, midPoint, endPoint);
    if (!arc.IsValid())
        return false;

    arcOut = arc;
    lengthOut = std::fabs(arc.Length());
    return std::isfinite(lengthOut);
}

static std::string OppositeSideToken(const std::string& side)
{
    if (_stricmp(side.c_str(), "left") == 0)
        return "right";
    if (_stricmp(side.c_str(), "right") == 0)
        return "left";
    return std::string();
}

static bool TryGetCornerEndpointMetadata(
    const nlohmann::json& key,
    std::string& roadOut,
    std::string& physicalSideOut,
    std::string& armDirectionOut)
{
    roadOut.clear();
    physicalSideOut.clear();
    armDirectionOut.clear();

    if (!key.is_object())
        return false;

    const std::string road = key.value("road", std::string());
    const std::string side = key.value("side", std::string());
    const std::string armId = key.value("armId", std::string());
    if (road.empty() || side.empty() || armId.empty())
        return false;

    if (armId.size() >= 9 && _stricmp(armId.c_str() + armId.size() - 9, ":backward") == 0)
        armDirectionOut = "backward";
    else if (armId.size() >= 8 && _stricmp(armId.c_str() + armId.size() - 8, ":forward") == 0)
        armDirectionOut = "forward";
    else
        return false;

    roadOut = road;
    physicalSideOut =
        _stricmp(armDirectionOut.c_str(), "backward") == 0
            ? OppositeSideToken(side)
            : side;
    return !physicalSideOut.empty();
}

static void ApplyCornerPairingMetadata(
    ON_3dmObjectAttributes& attrs,
    const nlohmann::json& cornerPairings,
    int cornerOrder)
{
    if (!cornerPairings.is_array() || cornerOrder < 0)
        return;

    for (const auto& pairing : cornerPairings)
    {
        if (!pairing.is_object() || pairing.value("cornerOrder", -1) != cornerOrder)
            continue;

        for (const char* endpointName : { "incoming", "outgoing" })
        {
            const auto endpointIt = pairing.find(endpointName);
            if (endpointIt == pairing.end())
                continue;

            std::string road;
            std::string physicalSide;
            std::string armDirection;
            if (!TryGetCornerEndpointMetadata(*endpointIt, road, physicalSide, armDirection))
                continue;

            attrs.SetUserString(
                Utf8ToWide(std::string("rook_corner_") + endpointName + "_road"),
                Utf8ToWide(road));
            attrs.SetUserString(
                Utf8ToWide(std::string("rook_corner_") + endpointName + "_side"),
                Utf8ToWide(physicalSide));
            attrs.SetUserString(
                Utf8ToWide(std::string("rook_corner_") + endpointName + "_arm_direction"),
                Utf8ToWide(armDirection));
        }

        break;
    }
}

static std::unique_ptr<ON_Brep> TryBuildPlanarBoundaryBrep(const ON_Polyline& polygon, double tolerance)
{
    if (polygon.Count() < 4)
        return nullptr;

    ON_PolylineCurve boundaryCurve(polygon);
    ON_SimpleArray<const ON_Curve*> inputLoops;
    inputLoops.Append(&boundaryCurve);

    ON_SimpleArray<ON_Brep*> breps;
    const double planarTolerance = tolerance > 0.0 ? tolerance : 1e-6;
    const bool ok = RhinoMakePlanarBreps(inputLoops, breps, planarTolerance, nullptr) ? true : false;
    if (!ok || breps.Count() != 1)
    {
        for (int i = 0; i < breps.Count(); ++i)
            delete breps[i];
        return nullptr;
    }

    ON_Brep* result = breps[0];
    for (int i = 1; i < breps.Count(); ++i)
        delete breps[i];

    return std::unique_ptr<ON_Brep>(result);
}

static std::wstring Utf8StringToWide(const std::string& input)
{
    if (input.empty())
        return std::wstring();

    const int size = ::MultiByteToWideChar(CP_UTF8, 0, input.c_str(), -1, nullptr, 0);
    if (size <= 0)
        return std::wstring();

    std::wstring result(size - 1, L'\0');
    ::MultiByteToWideChar(CP_UTF8, 0, input.c_str(), -1, result.data(), size);
    return result;
}

static std::string FormatWinHttpError(const char* step, DWORD errorCode)
{
    std::ostringstream message;
    message << step << " failed (WinHTTP " << errorCode << ")";

    LPWSTR buffer = nullptr;
    const DWORD flags = FORMAT_MESSAGE_ALLOCATE_BUFFER |
        FORMAT_MESSAGE_FROM_SYSTEM |
        FORMAT_MESSAGE_IGNORE_INSERTS;
    const DWORD size = ::FormatMessageW(
        flags,
        nullptr,
        errorCode,
        0,
        reinterpret_cast<LPWSTR>(&buffer),
        0,
        nullptr);

    if (size != 0 && buffer != nullptr)
    {
        std::wstring text(buffer, size);
        ::LocalFree(buffer);

        while (!text.empty() && (text.back() == L'\r' || text.back() == L'\n'))
            text.pop_back();

        const auto utf8 = WideToUtf8(text.c_str());
        if (!utf8.empty())
            message << ": " << utf8;
    }

    return message.str();
}

static bool QueryResponseStatusCode(HINTERNET request, int& statusCode)
{
    DWORD size = sizeof(DWORD);
    DWORD status = 0;
    if (!::WinHttpQueryHeaders(
        request,
        WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
        WINHTTP_HEADER_NAME_BY_INDEX,
        &status,
        &size,
        WINHTTP_NO_HEADER_INDEX))
    {
        return false;
    }

    statusCode = static_cast<int>(status);
    return true;
}

static bool TryReadJsonFile(const fs::path& path, nlohmann::json& out, std::string& error)
{
    try
    {
        std::ifstream file(path);
        if (!file.is_open())
        {
            error = "Failed to open discovery file: " + path.u8string();
            return false;
        }

        file >> out;
        return true;
    }
    catch (const std::exception& ex)
    {
        error = ex.what();
        return false;
    }
}

static bool TryGetRoadCreatorPortForCurrentProcess(int& port, std::string& host, std::string& error)
{
    try
    {
        const DWORD currentPid = ::GetCurrentProcessId();
        const fs::path discoveryFolder = fs::temp_directory_path() / "rook";
        if (!fs::exists(discoveryFolder))
        {
            error = "RoadCreator bridge discovery folder does not exist.";
            return false;
        }

        for (const auto& entry : fs::directory_iterator(discoveryFolder))
        {
            if (!entry.is_regular_file())
                continue;

            const auto filename = entry.path().filename().u8string();
            if (filename.rfind("instance-rc-", 0) != 0 || entry.path().extension() != ".json")
                continue;

            nlohmann::json info;
            std::string parseError;
            if (!TryReadJsonFile(entry.path(), info, parseError))
                continue;

            if (!info.is_object())
                continue;
            if (!info.contains("processId") || !info["processId"].is_number_integer())
                continue;
            if (static_cast<DWORD>(info["processId"].get<int>()) != currentPid)
                continue;
            if (!info.contains("port") || !info["port"].is_number_integer())
                continue;

            port = info["port"].get<int>();
            host = info.value("host", "127.0.0.1");
            return true;
        }

        error = "No RoadCreator bridge discovery file found for this Rhino process.";
        return false;
    }
    catch (const std::exception& ex)
    {
        error = ex.what();
        return false;
    }
}

static bool TryEnsureRoadCreatorPortForCurrentProcess(int& port, std::string& host, std::string& error)
{
    if (TryGetRoadCreatorPortForCurrentProcess(port, host, error))
        return true;

    std::string discoveryError = error;
    try
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([]() -> bool
        {
            CRhinoPlugIn::SaveLoadProtectionToRegistry(g_RookRoadsPlugInId, 1);
            return CRhinoPlugIn::LoadPlugIn(g_RookRoadsPlugInId, true, true) >= 0;
        });

        if (!future.get())
        {
            error = "RookRoads LoadPlugIn failed.";
            return false;
        }
    }
    catch (const std::exception& ex)
    {
        error = ex.what();
        return false;
    }

    for (int poll = 0; poll < 10; ++poll)
    {
        std::this_thread::sleep_for(std::chrono::milliseconds(250));
        std::string pollError;
        if (TryGetRoadCreatorPortForCurrentProcess(port, host, pollError))
            return true;
        discoveryError = pollError;
    }

    error = "RookRoads loaded but did not publish discovery for this Rhino process. " + discoveryError;
    return false;
}

static bool TryPostRoadCreatorJson(
    int port,
    const std::string& host,
    const std::string& path,
    const nlohmann::json& requestBody,
    int& statusCode,
    nlohmann::json& responseBody,
    std::string& error)
{
    const std::wstring target = Utf8StringToWide(path);
    if (target.empty())
    {
        error = "Failed to build RoadCreator bridge target path.";
        return false;
    }

    const std::wstring wideHost = Utf8StringToWide(host);
    if (wideHost.empty())
    {
        error = "Failed to convert RoadCreator host to wide string.";
        return false;
    }

    const std::string requestText = requestBody.dump();

    HINTERNET session = ::WinHttpOpen(
        L"RookNative/1.0",
        WINHTTP_ACCESS_TYPE_NO_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0);
    if (!session)
    {
        error = FormatWinHttpError("WinHttpOpen", ::GetLastError());
        return false;
    }

    HINTERNET connection = nullptr;
    HINTERNET request = nullptr;
    auto closeHandles = [&]() {
        if (request) ::WinHttpCloseHandle(request);
        if (connection) ::WinHttpCloseHandle(connection);
        if (session) ::WinHttpCloseHandle(session);
    };

    connection = ::WinHttpConnect(session, wideHost.c_str(), static_cast<INTERNET_PORT>(port), 0);
    if (!connection)
    {
        error = FormatWinHttpError("WinHttpConnect", ::GetLastError());
        closeHandles();
        return false;
    }

    request = ::WinHttpOpenRequest(
        connection,
        L"POST",
        target.c_str(),
        nullptr,
        WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES,
        0);
    if (!request)
    {
        error = FormatWinHttpError("WinHttpOpenRequest", ::GetLastError());
        closeHandles();
        return false;
    }

    ::WinHttpSetTimeouts(request, 2000, 2000, 30000, 120000);

    const wchar_t* headers = L"Accept: application/json\r\nContent-Type: application/json\r\n";
    LPVOID optionalBody = requestText.empty() ? WINHTTP_NO_REQUEST_DATA : const_cast<char*>(requestText.data());
    const DWORD optionalBodyLength = static_cast<DWORD>(requestText.size());

    if (!::WinHttpSendRequest(
        request,
        headers,
        static_cast<DWORD>(-1),
        optionalBody,
        optionalBodyLength,
        optionalBodyLength,
        0))
    {
        error = FormatWinHttpError("WinHttpSendRequest", ::GetLastError());
        closeHandles();
        return false;
    }

    if (!::WinHttpReceiveResponse(request, nullptr))
    {
        error = FormatWinHttpError("WinHttpReceiveResponse", ::GetLastError());
        closeHandles();
        return false;
    }

    if (!QueryResponseStatusCode(request, statusCode))
    {
        error = FormatWinHttpError("WinHttpQueryHeaders(status)", ::GetLastError());
        closeHandles();
        return false;
    }

    std::string responseText;
    for (;;)
    {
        DWORD available = 0;
        if (!::WinHttpQueryDataAvailable(request, &available))
        {
            error = FormatWinHttpError("WinHttpQueryDataAvailable", ::GetLastError());
            closeHandles();
            return false;
        }

        if (available == 0)
            break;

        std::string chunk(available, '\0');
        DWORD downloaded = 0;
        if (!::WinHttpReadData(request, chunk.data(), available, &downloaded))
        {
            error = FormatWinHttpError("WinHttpReadData", ::GetLastError());
            closeHandles();
            return false;
        }

        chunk.resize(downloaded);
        responseText += chunk;
    }

    closeHandles();

    try
    {
        responseBody = responseText.empty()
            ? nlohmann::json::object()
            : nlohmann::json::parse(responseText);
        return true;
    }
    catch (const std::exception& ex)
    {
        error = std::string("Failed to parse RoadCreator bridge response JSON: ") + ex.what();
        return false;
    }
}

static nlohmann::json BuildRoadCreatorIntersectionRealizationRequest(
    const std::string& analysisToken,
    const std::string& targetLayerRoot,
    const std::string& namePrefix,
    bool writeApproachEdges,
    bool writeApproachPatches,
    bool writeDebugDots,
    const nlohmann::json& analysis)
{
    nlohmann::json request;
    request["schema"] = "roadcreator.intersection-realization-request/v1";
    request["analysisToken"] = analysisToken;
    request["targetLayerRoot"] = targetLayerRoot;
    request["namePrefix"] = namePrefix;
    request["realizationMode"] = "planar_surface_with_analysis_guides";
    request["analysisStage"] = analysis.value("analysisStage", std::string());
    if (analysis.contains("selectedCandidate")
        && analysis["selectedCandidate"].is_object()
        && analysis["selectedCandidate"].contains("candidateId"))
    {
        request["selectedCandidate"] = analysis["selectedCandidate"];
    }
    request["sourceRoads"] = nlohmann::json::array();
    if (analysis.contains("centerlineA")
        && analysis["centerlineA"].is_string()
        && analysis.contains("profileA")
        && analysis["profileA"].is_object()
        && analysis["profileA"].contains("carriagewayEdgeOffset")
        && analysis.contains("selectedCandidate")
        && analysis["selectedCandidate"].is_object())
    {
        request["sourceRoads"].push_back({
            { "road", "A" },
            { "centerlineId", analysis["centerlineA"] },
            { "profileName", analysis["profileA"].value("name", std::string()) },
            { "symmetric", analysis["profileA"].value("symmetric", true) },
            { "requiresSideSelection", analysis["profileA"].value("requiresSideSelection", false) },
            { "resolvedSide", analysis.value("asymmetricSideA", std::string()) },
            { "carriagewayEdgeOffset", analysis["profileA"].value("carriagewayEdgeOffset", 0.0) },
            { "carriagewaySurfaceOffset", analysis["profileA"].value("carriagewaySurfaceOffset", analysis["profileA"].value("carriagewayEdgeOffset", 0.0)) },
            { "curbReturnDriverOffset", analysis["profileA"].value("curbReturnDriverOffset", analysis["profileA"].value("carriagewayEdgeOffset", 0.0)) },
            { "outerEnvelopeOffset", analysis["profileA"].value("outerEnvelopeOffset", analysis["profileA"].value("maxOffset", analysis["profileA"].value("carriagewayEdgeOffset", 0.0))) },
            { "armLengthOuterEnvelopeMultiplier", analysis["profileA"].value("armLengthOuterEnvelopeMultiplier", 0.0) },
            { "armLengthCarriagewayMultiplier", analysis["profileA"].value("armLengthCarriagewayMultiplier", 0.0) },
            { "armLengthDiagonalMultiplier", analysis["profileA"].value("armLengthDiagonalMultiplier", 0.0) },
            { "armLengthRadiusMultiplier", analysis["profileA"].value("armLengthRadiusMultiplier", 0.0) },
            { "armLengthMin", analysis["profileA"].value("armLengthMin", 0.0) },
            { "armLengthMax", analysis["profileA"].value("armLengthMax", 0.0) },
            { "selectedParameter", analysis["selectedCandidate"].value("parameterA", 0.0) },
            { "forwardTangent", analysis["selectedCandidate"].value("tangentA", nlohmann::json::array({ 1.0, 0.0, 0.0 })) }
        });
    }
    if (analysis.contains("centerlineB")
        && analysis["centerlineB"].is_string()
        && analysis.contains("profileB")
        && analysis["profileB"].is_object()
        && analysis["profileB"].contains("carriagewayEdgeOffset")
        && analysis.contains("selectedCandidate")
        && analysis["selectedCandidate"].is_object())
    {
        request["sourceRoads"].push_back({
            { "road", "B" },
            { "centerlineId", analysis["centerlineB"] },
            { "profileName", analysis["profileB"].value("name", std::string()) },
            { "symmetric", analysis["profileB"].value("symmetric", true) },
            { "requiresSideSelection", analysis["profileB"].value("requiresSideSelection", false) },
            { "resolvedSide", analysis.value("asymmetricSideB", std::string()) },
            { "carriagewayEdgeOffset", analysis["profileB"].value("carriagewayEdgeOffset", 0.0) },
            { "carriagewaySurfaceOffset", analysis["profileB"].value("carriagewaySurfaceOffset", analysis["profileB"].value("carriagewayEdgeOffset", 0.0)) },
            { "curbReturnDriverOffset", analysis["profileB"].value("curbReturnDriverOffset", analysis["profileB"].value("carriagewayEdgeOffset", 0.0)) },
            { "outerEnvelopeOffset", analysis["profileB"].value("outerEnvelopeOffset", analysis["profileB"].value("maxOffset", analysis["profileB"].value("carriagewayEdgeOffset", 0.0))) },
            { "armLengthOuterEnvelopeMultiplier", analysis["profileB"].value("armLengthOuterEnvelopeMultiplier", 0.0) },
            { "armLengthCarriagewayMultiplier", analysis["profileB"].value("armLengthCarriagewayMultiplier", 0.0) },
            { "armLengthDiagonalMultiplier", analysis["profileB"].value("armLengthDiagonalMultiplier", 0.0) },
            { "armLengthRadiusMultiplier", analysis["profileB"].value("armLengthRadiusMultiplier", 0.0) },
            { "armLengthMin", analysis["profileB"].value("armLengthMin", 0.0) },
            { "armLengthMax", analysis["profileB"].value("armLengthMax", 0.0) },
            { "selectedParameter", analysis["selectedCandidate"].value("parameterB", 0.0) },
            { "forwardTangent", analysis["selectedCandidate"].value("tangentB", nlohmann::json::array({ 0.0, 1.0, 0.0 })) }
        });
    }
    request["provisionalBoundary2D"] = analysis["provisionalBoundary2D"];
    request["analysisGeometry2D"] = analysis["analysisGeometry2D"];
    request["cornerPairings"] = analysis.value("cornerPairings", nlohmann::json::array());
    request["trimDecisions"] = analysis.value("trimDecisions", nlohmann::json::array());
    request["featureRules"] = analysis.value("featureRules", nlohmann::json::array());
    request["boundaryWalk"] = analysis.value("boundaryWalk", nlohmann::json::array());
    request["unresolvedConditions"] = analysis.value("unresolvedConditions", nlohmann::json::array());
    request["debugArtifacts"] = {
        { "writeGuides", true },
        { "writeApproachEdges", writeApproachEdges },
        { "writeApproachPatches", writeApproachPatches },
        { "writeDebugDots", writeDebugDots }
    };
    return request;
}

static bool TryRoadCreatorRealizationForActiveDoc(unsigned int docSn, std::string& error)
{
    try
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([docSn]() -> bool
        {
            CRhinoDoc* requestedDoc = ResolveDoc(docSn);
            CRhinoDoc* activeDoc = RhinoApp().ActiveDoc();
            return requestedDoc != nullptr
                && activeDoc != nullptr
                && requestedDoc->RuntimeSerialNumber() == activeDoc->RuntimeSerialNumber();
        });
        if (future.get())
            return true;

        error = "RoadCreator bridge currently realizes only into Rhino's active document.";
        return false;
    }
    catch (const std::exception& ex)
    {
        error = ex.what();
        return false;
    }
}

static bool TryCommitRoadIntersectionViaRoadCreator(
    unsigned int analysisDocSn,
    const std::string& analysisToken,
    const std::string& targetLayerRoot,
    const std::string& namePrefix,
    bool writeApproachEdges,
    bool writeApproachPatches,
    bool writeDebugDots,
    const nlohmann::json& analysis,
    nlohmann::json& resultOut,
    std::string& error)
{
    try
    {
        if (!TryRoadCreatorRealizationForActiveDoc(analysisDocSn, error))
            return false;

        int port = 0;
        std::string host = "127.0.0.1";
        if (!TryEnsureRoadCreatorPortForCurrentProcess(port, host, error))
            return false;

        int statusCode = 0;
        nlohmann::json envelope;
        if (!TryPostRoadCreatorJson(
                port,
                host,
                "/rc/intersection/realize",
                BuildRoadCreatorIntersectionRealizationRequest(
                    analysisToken,
                    targetLayerRoot,
                    namePrefix,
                    writeApproachEdges,
                    writeApproachPatches,
                    writeDebugDots,
                    analysis),
                statusCode,
                envelope,
                error))
        {
            return false;
        }

        if (statusCode < 200 || statusCode >= 300)
        {
            if (envelope.is_object() && envelope.contains("data") && envelope["data"].is_string())
                error = envelope["data"].get<std::string>();
            else if (error.empty())
                error = "RoadCreator bridge returned HTTP " + std::to_string(statusCode);
            return false;
        }

        if (!envelope.is_object())
        {
            error = "RoadCreator bridge returned a non-object response.";
            return false;
        }

        if (!envelope.value("success", false))
        {
            if (envelope.contains("data") && envelope["data"].is_string())
                error = envelope["data"].get<std::string>();
            else
                error = "RoadCreator bridge reported failure.";
            return false;
        }

        if (!envelope.contains("data") || !envelope["data"].is_object())
        {
            error = "RoadCreator bridge did not return a data object.";
            return false;
        }

        resultOut = envelope["data"];
        if (resultOut.value("analysisToken", std::string()) != analysisToken)
        {
            error = "RoadCreator bridge returned a mismatched analysisToken.";
            return false;
        }

        resultOut["analysisTokenValidated"] = true;
        resultOut["realizationProvider"] = "roadcreator";
        if (!resultOut.contains("commitStage"))
            resultOut["commitStage"] = "planar-surface-and-guides-write";
        if (!resultOut.contains("realizationMode"))
            resultOut["realizationMode"] = "planar_surface_with_analysis_guides";
        if (!resultOut.contains("targetLayerRoot"))
            resultOut["targetLayerRoot"] = targetLayerRoot;
        if (!resultOut.contains("analysisStage"))
            resultOut["analysisStage"] = analysis.value("analysisStage", std::string());
        if (!resultOut.contains("unresolvedConditions"))
            resultOut["unresolvedConditions"] = analysis.value("unresolvedConditions", nlohmann::json::array());
        return true;
    }
    catch (const std::exception& ex)
    {
        error = ex.what();
        return false;
    }
}

static WriteResult CommitRoadIntersectionFromAnalysis(
    unsigned int analysisDocSn,
    const nlohmann::json& analysis,
    const std::string& analysisToken,
    const std::string& targetLayerRoot,
    const std::string& namePrefix,
    bool writeApproachEdges,
    bool writeApproachPatches,
    bool writeDebugDots)
{
    nlohmann::json delegatedResult;
    std::string delegatedError;
    if (TryCommitRoadIntersectionViaRoadCreator(
            analysisDocSn,
            analysisToken,
            targetLayerRoot,
            namePrefix,
            writeApproachEdges,
            writeApproachPatches,
            writeDebugDots,
            analysis,
            delegatedResult,
            delegatedError))
    {
        WriteResult result;
        result.success = true;
        result.data = std::move(delegatedResult);
        return result;
    }

    if (!delegatedError.empty())
    {
        if (writeApproachEdges || writeApproachPatches || writeDebugDots)
        {
            WriteResult result;
            result.success = false;
            result.error = "Extended approach realization requires the RoadCreator adapter path. " + delegatedError;
            return result;
        }

        RhinoApp().Print(
            L"RookNative: RoadCreator intersection realization unavailable for token %S. Falling back to native commit. %S\n",
            analysisToken.c_str(),
            delegatedError.c_str());
    }

    auto nativeFuture = CMainThreadDispatcher::Instance().Dispatch(
        [analysisDocSn, analysis, analysisToken, targetLayerRoot, namePrefix]() -> WriteResult
    {
        return CommitRoadIntersectionNative(
            analysisDocSn,
            analysis,
            analysisToken,
            targetLayerRoot,
            namePrefix);
    });

    return nativeFuture.get();
}

static WriteResult CommitRoadIntersectionNative(
    unsigned int analysisDocSn,
    const nlohmann::json& analysis,
    const std::string& analysisToken,
    const std::string& targetLayerRoot,
    const std::string& namePrefix)
{
    CRhinoDoc* pDoc = ResolveDoc(analysisDocSn);
    UndoScope undo(pDoc, L"Commit Road Intersection 2D Analysis");

    const int analysisLayerIndex = EnsureLayerPath(pDoc, targetLayerRoot + "::Analysis");
    const int boundaryLayerIndex = EnsureLayerPath(pDoc, targetLayerRoot + "::Boundary");
    const int curbReturnsLayerIndex = EnsureLayerPath(pDoc, targetLayerRoot + "::Curb Returns");
    const int surfaceLayerIndex = EnsureLayerPath(pDoc, targetLayerRoot + "::Surface");

    nlohmann::json createdIds = nlohmann::json::array();
    nlohmann::json boundarySegmentIds = nlohmann::json::array();
    nlohmann::json curbReturnArcIds = nlohmann::json::array();
    nlohmann::json provisionalBoundaryPolygonId = nlohmann::json(nullptr);
    nlohmann::json realizedSurfaceId = nlohmann::json(nullptr);
    double boundaryLineLength = 0.0;
    double curbReturnArcLength = 0.0;
    double realizedSurfaceArea = analysis["provisionalBoundary2D"].value("area", 0.0);

    ON_Polyline polygon;
    for (const auto& pointJson : analysis["provisionalBoundary2D"]["cornerPoints"])
        polygon.Append(JsonValueToPoint3d(pointJson));
    if (polygon.Count() < 3)
        throw std::runtime_error("Not enough provisional boundary points to commit");
    if (polygon[0].DistanceTo(polygon[polygon.Count() - 1]) > 1e-6)
        polygon.Append(polygon[0]);

    const double planarTolerance = (std::max)(
        analysis.value("intersectionTolerance", pDoc->AbsoluteTolerance()),
        1e-6);
    std::unique_ptr<ON_Brep> realizedSurface = TryBuildPlanarBoundaryBrep(polygon, planarTolerance);
    if (!realizedSurface)
        throw std::runtime_error("Failed to build planar intersection surface from provisional boundary");

    ON_3dmObjectAttributes surfaceAttrs = MakeIntersectionArtifactAttributes(
        surfaceLayerIndex,
        namePrefix + "::surface",
        analysisToken,
        "realized_surface",
        "planar_surface_patch");
    if (CRhinoBrepObject* surfaceObj = pDoc->AddBrepObject(*realizedSurface, &surfaceAttrs))
    {
        const std::string id = UuidToString(surfaceObj->Attributes().m_uuid);
        realizedSurfaceId = id;
        createdIds.push_back(id);

        ON_MassProperties mp;
        if (realizedSurface->AreaMassProperties(mp, true, false, false, false))
        {
            const double area = mp.Area();
            if (std::isfinite(area))
                realizedSurfaceArea = RoundTo(area, 4);
        }
    }
    else
    {
        throw std::runtime_error("Failed to add realized surface patch");
    }

    ON_3dmObjectAttributes polygonAttrs = MakeIntersectionArtifactAttributes(
        analysisLayerIndex,
        namePrefix + "::provisional-boundary-polygon",
        analysisToken,
        "provisional_boundary_polygon");
    if (CRhinoCurveObject* polygonObj = pDoc->AddCurveObject(polygon, &polygonAttrs))
    {
        const std::string id = UuidToString(polygonObj->Attributes().m_uuid);
        provisionalBoundaryPolygonId = id;
        createdIds.push_back(id);
    }
    else
    {
        throw std::runtime_error("Failed to add provisional boundary polygon");
    }

    int segmentIndex = 0;
    for (const auto& segmentJson : analysis["analysisGeometry2D"]["boundarySegments"])
    {
        const ON_3dPoint startPoint = JsonValueToPoint3d(segmentJson["startPoint"]);
        const ON_3dPoint endPoint = JsonValueToPoint3d(segmentJson["endPoint"]);
        boundaryLineLength += startPoint.DistanceTo(endPoint);

        ON_LineCurve line(startPoint, endPoint);
        ON_3dmObjectAttributes attrs = MakeIntersectionArtifactAttributes(
            boundaryLayerIndex,
            namePrefix + "::boundary-segment-" + std::to_string(segmentIndex),
            analysisToken,
            "boundary_segment");
        attrs.SetUserString(L"rook_intersection_index", Utf8ToWide(std::to_string(segmentIndex)));

        CRhinoCurveObject* lineObj = pDoc->AddCurveObject(line, &attrs);
        if (!lineObj)
            throw std::runtime_error("Failed to add boundary segment " + std::to_string(segmentIndex));

        const std::string id = UuidToString(lineObj->Attributes().m_uuid);
        createdIds.push_back(id);
        boundarySegmentIds.push_back(id);
        ++segmentIndex;
    }

    int arcIndex = 0;
    for (const auto& arcJson : analysis["analysisGeometry2D"]["curbReturnArcs"])
    {
        ON_Arc arc;
        double arcLength = 0.0;
        if (!TryBuildCommittedArc(arcJson, arc, arcLength))
            throw std::runtime_error("Failed to realize curb return arc " + std::to_string(arcIndex));

        ON_3dmObjectAttributes attrs = MakeIntersectionArtifactAttributes(
            curbReturnsLayerIndex,
            namePrefix + "::curb-return-" + std::to_string(arcIndex),
            analysisToken,
            "curb_return_arc");
        attrs.SetUserString(L"rook_intersection_index", Utf8ToWide(std::to_string(arcIndex)));
        const int cornerOrder = arcJson.value("cornerOrder", -1);
        if (cornerOrder >= 0)
        {
            attrs.SetUserString(L"rook_intersection_corner", Utf8ToWide(std::to_string(cornerOrder)));
            ApplyCornerPairingMetadata(
                attrs,
                analysis.value("cornerPairings", nlohmann::json::array()),
                cornerOrder);
        }
        const ON_3dPoint incomingJoinPoint = JsonValueToPoint3d(arcJson.at("startPoint"));
        const ON_3dPoint outgoingJoinPoint = JsonValueToPoint3d(arcJson.at("endPoint"));
        attrs.SetUserString(
            L"rook_corner_incoming_join_point",
            Utf8ToWide(
                std::to_string(incomingJoinPoint.x) + ","
                + std::to_string(incomingJoinPoint.y) + ","
                + std::to_string(incomingJoinPoint.z)));
        attrs.SetUserString(
            L"rook_corner_outgoing_join_point",
            Utf8ToWide(
                std::to_string(outgoingJoinPoint.x) + ","
                + std::to_string(outgoingJoinPoint.y) + ","
                + std::to_string(outgoingJoinPoint.z)));

        CRhinoCurveObject* arcObj = pDoc->AddCurveObject(arc, &attrs);
        if (!arcObj)
            throw std::runtime_error("Failed to add curb return arc object " + std::to_string(arcIndex));

        const std::string id = UuidToString(arcObj->Attributes().m_uuid);
        createdIds.push_back(id);
        curbReturnArcIds.push_back(id);
        curbReturnArcLength += arcLength;
        ++arcIndex;
    }

    pDoc->Redraw();

    std::set<std::string> fallbackCodes;
    nlohmann::json fallbackFlags = nlohmann::json::array();
    for (const auto& condition : analysis["unresolvedConditions"])
    {
        const std::string code = condition.value("code", std::string());
        if (!code.empty() && fallbackCodes.insert(code).second)
            fallbackFlags.push_back(code);
    }

    WriteResult wr;
    wr.success = true;
    wr.data["analysisToken"] = analysisToken;
    wr.data["analysisTokenValidated"] = true;
    wr.data["realizationProvider"] = "native-fallback";
    wr.data["commitStage"] = "planar-surface-and-guides-write";
    wr.data["realizationMode"] = "planar_surface_with_analysis_guides";
    wr.data["targetLayerRoot"] = targetLayerRoot;
    wr.data["layerPaths"] = {
        { "analysis", GetLayerFullPathUtf8(pDoc, analysisLayerIndex) },
        { "boundary", GetLayerFullPathUtf8(pDoc, boundaryLayerIndex) },
        { "curbReturns", GetLayerFullPathUtf8(pDoc, curbReturnsLayerIndex) },
        { "surface", GetLayerFullPathUtf8(pDoc, surfaceLayerIndex) }
    };
    wr.data["createdCount"] = createdIds.size();
    wr.data["createdIds"] = std::move(createdIds);
    wr.data["created"] = {
        { "realizedSurfaceId", realizedSurfaceId },
        { "provisionalBoundaryPolygonId", provisionalBoundaryPolygonId },
        { "boundarySegmentIds", std::move(boundarySegmentIds) },
        { "curbReturnArcIds", std::move(curbReturnArcIds) }
    };
    wr.data["summaries"] = {
        { "area", analysis["provisionalBoundary2D"].value("area", 0.0) },
        { "surfaceArea", realizedSurfaceArea },
        { "boundaryLineLength", RoundTo(boundaryLineLength, 4) },
        { "curbReturnArcLength", RoundTo(curbReturnArcLength, 4) }
    };
    wr.data["fallbackFlags"] = std::move(fallbackFlags);
    wr.data["analysisStage"] = analysis.value("analysisStage", std::string());
    wr.data["unresolvedConditions"] = analysis["unresolvedConditions"];
    return wr;
}

void HandleRoadIntersectionCommit(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("analysisToken") || !body["analysisToken"].is_string())
    {
        CRookServer::SendError(res, "analysisToken is required");
        return;
    }
    if (!body.contains("targetLayerRoot") || !body["targetLayerRoot"].is_string())
    {
        CRookServer::SendError(res, "targetLayerRoot is required");
        return;
    }

    const std::string analysisToken = body["analysisToken"].get<std::string>();
    const std::string targetLayerRoot = body["targetLayerRoot"].get<std::string>();
    const std::string namePrefix = body.value("namePrefix", std::string("IntersectionAnalysis2D"));
    const bool writeApproachEdges = JsonBoolValueOrDefault(body, "writeApproachEdges", false);
    const bool writeApproachPatches = JsonBoolValueOrDefault(body, "writeApproachPatches", false);
    const bool writeDebugDots = JsonBoolValueOrDefault(body, "writeDebugDots", false);
    nlohmann::json analysisBody = body;
    unsigned int analysisDocSn = docSn;
    if (!analysisBody.contains("centerlineA") || !analysisBody.contains("centerlineB"))
    {
        CachedIntersectionAnalyzeRequest cachedRequest;
        if (!TryGetCachedIntersectionAnalyzeRequest(analysisToken, cachedRequest))
        {
            CRookServer::SendError(res, "analysisToken is not available in the analyze cache; rerun /road/intersection/analyze or provide the full analysis inputs");
            return;
        }

        analysisBody = cachedRequest.body;
        analysisDocSn = cachedRequest.docSn;
    }

    ON_UUID centerlineA;
    ON_UUID centerlineB;
    try
    {
        centerlineA = ParseUuid(analysisBody, "centerlineA");
        centerlineB = ParseUuid(analysisBody, "centerlineB");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    const std::string profileA = analysisBody.value("profileA", std::string());
    const std::string profileB = analysisBody.value("profileB", std::string());
    const std::string asymmetricSideA = NormalizeSideToken(analysisBody.value("asymmetricSideA", std::string()));
    const std::string asymmetricSideB = NormalizeSideToken(analysisBody.value("asymmetricSideB", std::string()));
    if (analysisBody.contains("asymmetricSideA") && asymmetricSideA.empty())
    {
        CRookServer::SendError(res, "asymmetricSideA must be 'left' or 'right'");
        return;
    }
    if (analysisBody.contains("asymmetricSideB") && asymmetricSideB.empty())
    {
        CRookServer::SendError(res, "asymmetricSideB must be 'left' or 'right'");
        return;
    }

    std::vector<double> filletRadii;
    if (analysisBody.contains("filletRadii"))
    {
        if (!analysisBody["filletRadii"].is_array())
        {
            CRookServer::SendError(res, "filletRadii must be an array");
            return;
        }

        for (const auto& entry : analysisBody["filletRadii"])
        {
            const double radius = entry.get<double>();
            if (!std::isfinite(radius) || radius < 0.0)
            {
                CRookServer::SendError(res, "filletRadii values must be finite and non-negative");
                return;
            }
            filletRadii.push_back(RoundTo(radius, 4));
        }
    }

    const double toleranceOverride = analysisBody.value("tolerance", 0.0);
    const double overlapToleranceOverride = analysisBody.value("overlapTolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [analysisDocSn,
         analysisBody,
         centerlineA,
         centerlineB,
         profileA,
         profileB,
         asymmetricSideA,
         asymmetricSideB,
         toleranceOverride,
         overlapToleranceOverride,
         filletRadii = std::move(filletRadii)]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(analysisDocSn);

        std::unique_ptr<RoadProfileMetadata> metadataA;
        std::unique_ptr<RoadProfileMetadata> metadataB;
        if (!profileA.empty())
            metadataA = std::make_unique<RoadProfileMetadata>(
                LoadRoadProfileMetadata(pDoc, profileA));
        if (!profileB.empty())
            metadataB = std::make_unique<RoadProfileMetadata>(
                LoadRoadProfileMetadata(pDoc, profileB));

        return ComputeRoadIntersectionAnalyzeForCommit(
            analysisDocSn,
            analysisBody,
            centerlineA,
            centerlineB,
            asymmetricSideA,
            asymmetricSideB,
            toleranceOverride,
            overlapToleranceOverride,
            filletRadii,
            metadataA.get(),
            metadataB.get());
    });

    try
    {
        nlohmann::json analysis = future.get();
        if (analysis.value("analysisToken", std::string()) != analysisToken)
            throw std::runtime_error("analysisToken no longer matches the current source geometry and analysis inputs");
        if (!JsonBoolValueOrDefault(analysis, "readyForCommit", false))
            throw std::runtime_error("Current analysis is not ready for commit");
        const WriteResult commitResult = CommitRoadIntersectionFromAnalysis(
            analysisDocSn,
            analysis,
            analysisToken,
            targetLayerRoot,
            namePrefix,
            writeApproachEdges,
            writeApproachPatches,
            writeDebugDots);
        if (commitResult.success)
            CRookServer::SendSuccess(res, commitResult.data);
        else
            CRookServer::SendError(res, commitResult.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

void HandleRoadIntersectionResolve(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID centerlineA;
    ON_UUID centerlineB;
    try
    {
        centerlineA = ParseUuid(body, "centerlineA");
        centerlineB = ParseUuid(body, "centerlineB");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("targetLayerRoot") || !body["targetLayerRoot"].is_string())
    {
        CRookServer::SendError(res, "targetLayerRoot must be a string");
        return;
    }

    const std::string targetLayerRoot = body["targetLayerRoot"].get<std::string>();
    const std::string namePrefix = body.value("namePrefix", std::string("IntersectionAnalysis2D"));
    const bool writeApproachEdges = JsonBoolValueOrDefault(body, "writeApproachEdges", false);
    const bool writeApproachPatches = JsonBoolValueOrDefault(body, "writeApproachPatches", false);
    const bool writeDebugDots = JsonBoolValueOrDefault(body, "writeDebugDots", false);

    const std::string candidateMode = NormalizeCandidateModeToken(body.value("candidateMode", std::string("single")));
    if (candidateMode.empty())
    {
        CRookServer::SendError(res, "candidateMode must be 'single' or 'all'");
        return;
    }

    const std::string profileA = body.value("profileA", std::string());
    const std::string profileB = body.value("profileB", std::string());
    const std::string asymmetricSideA = NormalizeSideToken(body.value("asymmetricSideA", std::string()));
    const std::string asymmetricSideB = NormalizeSideToken(body.value("asymmetricSideB", std::string()));
    if (body.contains("asymmetricSideA") && asymmetricSideA.empty())
    {
        CRookServer::SendError(res, "asymmetricSideA must be 'left' or 'right'");
        return;
    }
    if (body.contains("asymmetricSideB") && asymmetricSideB.empty())
    {
        CRookServer::SendError(res, "asymmetricSideB must be 'left' or 'right'");
        return;
    }

    std::vector<double> filletRadii;
    if (body.contains("filletRadii"))
    {
        if (!body["filletRadii"].is_array())
        {
            CRookServer::SendError(res, "filletRadii must be an array");
            return;
        }

        for (const auto& entry : body["filletRadii"])
        {
            const double radius = entry.get<double>();
            if (!std::isfinite(radius) || radius < 0.0)
            {
                CRookServer::SendError(res, "filletRadii values must be finite and non-negative");
                return;
            }
            filletRadii.push_back(RoundTo(radius, 4));
        }
    }

    const double toleranceOverride = body.value("tolerance", 0.0);
    const double overlapToleranceOverride = body.value("overlapTolerance", 0.0);

    // Load profiles on the main thread (reads doc user text, falls back to filesystem).
    // Loaded here so that metadataA/metadataB stay alive across both Dispatch calls below.
    std::unique_ptr<RoadProfileMetadata> metadataA;
    std::unique_ptr<RoadProfileMetadata> metadataB;
    try
    {
        auto profileFuture = CMainThreadDispatcher::Instance().Dispatch(
            [docSn, profileA, profileB]() -> std::pair<
                std::unique_ptr<RoadProfileMetadata>,
                std::unique_ptr<RoadProfileMetadata>>
        {
            CRhinoDoc* pDoc = ResolveDoc(docSn);
            std::unique_ptr<RoadProfileMetadata> a;
            std::unique_ptr<RoadProfileMetadata> b;
            if (!profileA.empty())
                a = std::make_unique<RoadProfileMetadata>(
                    LoadRoadProfileMetadata(pDoc, profileA));
            if (!profileB.empty())
                b = std::make_unique<RoadProfileMetadata>(
                    LoadRoadProfileMetadata(pDoc, profileB));
            return { std::move(a), std::move(b) };
        });
        auto [a, b] = profileFuture.get();
        metadataA = std::move(a);
        metadataB = std::move(b);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto candidateFuture = CMainThreadDispatcher::Instance().Dispatch(
        [docSn,
         centerlineA,
         centerlineB,
         toleranceOverride,
         overlapToleranceOverride,
         metadataA = metadataA.get(),
         metadataB = metadataB.get()]() -> CandidateComputationResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const CRhinoObject* objA = pDoc->LookupObject(centerlineA);
        const CRhinoObject* objB = pDoc->LookupObject(centerlineB);
        if (!objA || !objB)
            throw std::invalid_argument("One or both centerline objects not found");

        const ON_Curve* curveA = ON_Curve::Cast(objA->Geometry());
        const ON_Curve* curveB = ON_Curve::Cast(objB->Geometry());
        if (!curveA || !curveB)
            throw std::invalid_argument("Both centerline objects must be curves");

        return ComputeRoadIntersectionCandidates(
            *curveA,
            *curveB,
            pDoc->AbsoluteTolerance(),
            toleranceOverride,
            overlapToleranceOverride,
            metadataA,
            metadataB);
    });

    try
    {
        const CandidateComputationResult candidateResult = candidateFuture.get();

        nlohmann::json result;
        result["schema"] = "rook.road-intersection-resolve-result/v1";
        result["centerlineA"] = UuidToString(centerlineA);
        result["centerlineB"] = UuidToString(centerlineB);
        if (metadataA)
            result["profileA"] = RoadProfileMetadataToJson(*metadataA);
        if (metadataB)
            result["profileB"] = RoadProfileMetadataToJson(*metadataB);
        result["candidateMode"] = candidateMode;
        result["candidateCount"] = static_cast<int>(candidateResult.candidates.size());
        result["overlapCount"] = candidateResult.overlapCount;
        result["recommendedCandidateId"] =
            candidateResult.recommendedCandidateId.empty()
                ? nlohmann::json(nullptr)
                : nlohmann::json(candidateResult.recommendedCandidateId);

        nlohmann::json candidatesJson = nlohmann::json::array();
        for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
            candidatesJson.push_back(CandidateToJson(candidateResult.candidates[i], i));
        result["candidates"] = std::move(candidatesJson);

        std::vector<size_t> selectedIndices;
        std::vector<std::string> selectionMethods;
        if (candidateMode == "all")
        {
            selectedIndices.reserve(candidateResult.candidates.size());
            selectionMethods.reserve(candidateResult.candidates.size());
            for (size_t i = 0; i < candidateResult.candidates.size(); ++i)
            {
                selectedIndices.push_back(i);
                selectionMethods.push_back("allCandidates");
            }
        }
        else
        {
            try
            {
                const auto [selectedIndex, selectionMethod] = SelectCandidateIndex(body, candidateResult);
                selectedIndices.push_back(selectedIndex);
                selectionMethods.push_back(selectionMethod);
            }
            catch (const std::invalid_argument& ex)
            {
                if (std::string(ex.what()).find("Multiple intersection candidates found;") == 0)
                {
                    result["executionMode"] = "candidate-selection-required";
                    result["requiresCandidateSelection"] = true;
                    result["selectionMessage"] = ex.what();
                    result["attemptedCandidateCount"] = 0;
                    result["successfulCandidateCount"] = 0;
                    result["failedCandidateCount"] = 0;
                    result["results"] = nlohmann::json::array();
                    CRookServer::SendSuccess(res, result);
                    return;
                }

                throw;
            }
        }

        const nlohmann::json requiredSideSelections = BuildRequiredSideSelectionsJson(
            metadataA.get(), asymmetricSideA, metadataB.get(), asymmetricSideB);
        if (!requiredSideSelections.empty())
        {
            result["executionMode"] = "side-selection-required";
            result["requiresCandidateSelection"] = false;
            result["requiresSideSelection"] = true;
            result["requiredSideSelections"] = requiredSideSelections;
            result["selectionMessage"] = "Provide asymmetricSideA/asymmetricSideB for any road listed in requiredSideSelections before resolving the intersection.";
            result["attemptedCandidateCount"] = 0;
            result["successfulCandidateCount"] = 0;
            result["failedCandidateCount"] = 0;
            result["results"] = nlohmann::json::array();
            CRookServer::SendSuccess(res, result);
            return;
        }

        result["executionMode"] = candidateMode == "all" ? "all" : "single";
        result["requiresCandidateSelection"] = false;
        result["requiresSideSelection"] = false;
        result["attemptedCandidateCount"] = static_cast<int>(selectedIndices.size());

        nlohmann::json entries = nlohmann::json::array();
        int successfulCandidateCount = 0;
        int failedCandidateCount = 0;
        const bool useNestedCandidateLayers = (candidateMode == "all" && selectedIndices.size() > 1);

        for (size_t i = 0; i < selectedIndices.size(); ++i)
        {
            const size_t selectedIndex = selectedIndices[i];
            const std::string candidateId = "cand-" + std::to_string(selectedIndex);
            const std::string selectionMethod = selectionMethods[i];
            const std::string candidateLayerRoot = useNestedCandidateLayers
                ? targetLayerRoot + "::" + candidateId
                : targetLayerRoot;

            nlohmann::json analysisBody = body;
            analysisBody["candidateId"] = candidateId;

            auto analysisFuture = CMainThreadDispatcher::Instance().Dispatch(
                [docSn,
                 analysisBody,
                 centerlineA,
                 centerlineB,
                 asymmetricSideA,
                 asymmetricSideB,
                 toleranceOverride,
                 overlapToleranceOverride,
                 filletRadii,
                 metadataA = metadataA.get(),
                 metadataB = metadataB.get()]() -> nlohmann::json
            {
                return ComputeRoadIntersectionAnalyzeForCommit(
                    docSn,
                    analysisBody,
                    centerlineA,
                    centerlineB,
                    asymmetricSideA,
                    asymmetricSideB,
                    toleranceOverride,
                    overlapToleranceOverride,
                    filletRadii,
                    metadataA,
                    metadataB);
            });

            nlohmann::json entry;
            entry["candidateId"] = candidateId;
            entry["selectionMethod"] = selectionMethod;
            entry["targetLayerRoot"] = candidateLayerRoot;

            try
            {
                nlohmann::json analysis = analysisFuture.get();
                entry["analysisToken"] = analysis.value("analysisToken", std::string());
                entry["analysisStage"] = analysis.value("analysisStage", std::string());
                entry["selectedCandidate"] = analysis.value("selectedCandidate", nlohmann::json::object());
                entry["readyForCommit"] = JsonBoolValueOrDefault(analysis, "readyForCommit", false);
                entry["topologyReadyForGeometry"] = JsonBoolValueOrDefault(analysis, "topologyReadyForGeometry", false);
                entry["unresolvedConditions"] = analysis.value("unresolvedConditions", nlohmann::json::array());

                CacheIntersectionAnalyzeRequest(entry["analysisToken"].get<std::string>(), docSn, analysisBody);

                if (!entry["readyForCommit"].get<bool>())
                {
                    entry["success"] = false;
                    entry["error"] = "Selected candidate analysis is not ready for commit";
                    ++failedCandidateCount;
                    entries.push_back(std::move(entry));
                    continue;
                }

                const WriteResult commitResult = CommitRoadIntersectionFromAnalysis(
                    docSn,
                    analysis,
                    entry["analysisToken"].get<std::string>(),
                    candidateLayerRoot,
                    namePrefix,
                    writeApproachEdges,
                    writeApproachPatches,
                    writeDebugDots);

                if (commitResult.success)
                {
                    entry["success"] = true;
                    entry["commit"] = commitResult.data;
                    ++successfulCandidateCount;
                }
                else
                {
                    entry["success"] = false;
                    entry["error"] = commitResult.error;
                    ++failedCandidateCount;
                }
            }
            catch (const std::exception& ex)
            {
                entry["success"] = false;
                entry["error"] = ex.what();
                ++failedCandidateCount;
            }

            entries.push_back(std::move(entry));
        }

        result["successfulCandidateCount"] = successfulCandidateCount;
        result["failedCandidateCount"] = failedCandidateCount;
        result["results"] = std::move(entries);
        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

void HandleIntersectCurves(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID id1, id2;
    try { id1 = ParseUuid(body, "id1"); id2 = ParseUuid(body, "id2"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, id1, id2]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const CRhinoObject* obj1 = pDoc->LookupObject(id1);
        const CRhinoObject* obj2 = pDoc->LookupObject(id2);
        if (!obj1 || !obj2)
            throw std::invalid_argument("One or both objects not found");

        const ON_Curve* curve1 = ON_Curve::Cast(obj1->Geometry());
        const ON_Curve* curve2 = ON_Curve::Cast(obj2->Geometry());
        if (!curve1 || !curve2)
            throw std::invalid_argument("Both objects must be curves");

        // Select both curves, run _-Intersect, track new objects
        SelectObjects(pDoc, {id1, id2});
        ObjectDiffTracker tracker(pDoc);

        const bool scriptOk = RhinoApp().RunScript(
            pDoc->RuntimeSerialNumber(),
            L"_-Intersect _Enter", 0);
        if (!scriptOk)
            throw std::runtime_error("Rhino _Intersect command failed for curve-curve intersection");

        auto newIds = tracker.GetNewObjects();

        // Classify new objects as points or curves
        nlohmann::json points = nlohmann::json::array();
        nlohmann::json overlapIds = nlohmann::json::array();

        for (const auto& nid : newIds)
        {
            const CRhinoObject* newObj = pDoc->LookupObject(nid);
            if (!newObj) continue;

            if (const ON_Point* pt = ON_Point::Cast(newObj->Geometry()))
            {
                nlohmann::json ptJ;
                ptJ["point"] = Point3dToJson(pt->point);
                points.push_back(std::move(ptJ));
            }
            else if (ON_Curve::Cast(newObj->Geometry()))
            {
                overlapIds.push_back(UuidToString(nid));
            }
        }

        WriteResult wr;
        wr.success = true;
        wr.data["intersectionCount"] = static_cast<int>(points.size());
        wr.data["overlapCount"] = static_cast<int>(overlapIds.size());
        wr.data["points"] = std::move(points);
        wr.data["overlapCurveIds"] = std::move(overlapIds);

        if (!newIds.empty())
            pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /intersect/curve-surface ───────────────────────────────
// Uses RunScript: RhinoCurveSurfaceIntersect is in blocked RhinoSdkIntersect.h

void HandleIntersectCurveSurface(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID curveId, surfaceId;
    try {
        curveId = ParseUuid(body, "curveId");
        surfaceId = ParseUuid(body, "surfaceId");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, curveId, surfaceId]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const CRhinoObject* crvObj = pDoc->LookupObject(curveId);
        const CRhinoObject* srfObj = pDoc->LookupObject(surfaceId);
        if (!crvObj || !srfObj)
            throw std::invalid_argument("Curve or surface object not found");

        if (!ON_Curve::Cast(crvObj->Geometry()))
            throw std::invalid_argument("First object is not a curve");

        // Select both objects, run _-Intersect, track new objects
        SelectObjects(pDoc, {curveId, surfaceId});
        ObjectDiffTracker tracker(pDoc);

        const bool scriptOk = RhinoApp().RunScript(
            pDoc->RuntimeSerialNumber(),
            L"_-Intersect _Enter", 0);
        if (!scriptOk)
            throw std::runtime_error("Rhino _Intersect command failed for curve-surface intersection");

        auto newIds = tracker.GetNewObjects();

        nlohmann::json points = nlohmann::json::array();
        nlohmann::json overlapIds = nlohmann::json::array();

        for (const auto& nid : newIds)
        {
            const CRhinoObject* newObj = pDoc->LookupObject(nid);
            if (!newObj) continue;

            if (const ON_Point* pt = ON_Point::Cast(newObj->Geometry()))
            {
                nlohmann::json ptJ;
                ptJ["point"] = Point3dToJson(pt->point);
                points.push_back(std::move(ptJ));
            }
            else if (ON_Curve::Cast(newObj->Geometry()))
            {
                overlapIds.push_back(UuidToString(nid));
            }
        }

        WriteResult wr;
        wr.success = true;
        wr.data["intersectionCount"] = static_cast<int>(points.size());
        wr.data["overlapCount"] = static_cast<int>(overlapIds.size());
        wr.data["points"] = std::move(points);
        wr.data["overlapCurveIds"] = std::move(overlapIds);

        if (!newIds.empty())
            pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /intersect/curve-brep ──────────────────────────────────

void HandleIntersectCurveBrep(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID curveId, brepId;
    try {
        curveId = ParseUuid(body, "curveId");
        brepId = ParseUuid(body, "brepId");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, curveId, brepId, tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double tol = (tolerance > 0.0) ? tolerance : pDoc->AbsoluteTolerance();

        const CRhinoObject* crvObj = pDoc->LookupObject(curveId);
        const CRhinoObject* brepObj = pDoc->LookupObject(brepId);
        if (!crvObj || !brepObj)
            throw std::invalid_argument("Curve or brep object not found");

        const ON_Curve* curve = ON_Curve::Cast(crvObj->Geometry());
        if (!curve)
            throw std::invalid_argument("First object is not a curve");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(brepObj->Geometry(), bMustDelete);
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);
        if (!brep)
            throw std::invalid_argument("Second object is not a brep/extrusion/surface");

        ON_SimpleArray<ON_Curve*> outCurves;
        ON_3dPointArray outPoints;
        RhinoCurveBrepIntersect(*curve, *brep, tol, outCurves, outPoints);

        UndoScope undo(pDoc, L"Intersect curve-brep");

        nlohmann::json pointsJson = nlohmann::json::array();
        for (int i = 0; i < outPoints.Count(); ++i)
            pointsJson.push_back(Point3dToJson(outPoints[i]));

        nlohmann::json overlapIds = nlohmann::json::array();
        for (int i = 0; i < outCurves.Count(); ++i)
        {
            if (outCurves[i])
            {
                CRhinoCurveObject* newObj = pDoc->AddCurveObject(*outCurves[i]);
                if (newObj)
                    overlapIds.push_back(UuidToString(newObj->Attributes().m_uuid));
                delete outCurves[i];
                outCurves[i] = nullptr;
            }
        }

        bool hasResults = (outPoints.Count() > 0 || outCurves.Count() > 0);

        WriteResult wr;
        wr.success = true;
        wr.data["intersectionCount"] = outPoints.Count();
        wr.data["overlapCount"] = static_cast<int>(overlapIds.size());
        wr.data["points"] = std::move(pointsJson);
        wr.data["overlapCurveIds"] = std::move(overlapIds);

        if (hasResults)
            pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /intersect/breps ──────────────────────────────────────

void HandleIntersectBreps(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID id1, id2;
    try { id1 = ParseUuid(body, "id1"); id2 = ParseUuid(body, "id2"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, id1, id2, tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double tol = (tolerance > 0.0) ? tolerance : pDoc->AbsoluteTolerance();

        const CRhinoObject* obj1 = pDoc->LookupObject(id1);
        const CRhinoObject* obj2 = pDoc->LookupObject(id2);
        if (!obj1 || !obj2)
            throw std::invalid_argument("One or both objects not found");

        bool bDel1 = false, bDel2 = false;
        const ON_Brep* brep1 = ExtractBrep(obj1->Geometry(), bDel1);
        std::unique_ptr<const ON_Brep> guard1(bDel1 ? brep1 : nullptr);
        const ON_Brep* brep2 = ExtractBrep(obj2->Geometry(), bDel2);
        std::unique_ptr<const ON_Brep> guard2(bDel2 ? brep2 : nullptr);

        if (!brep1 || !brep2)
            throw std::invalid_argument("Both objects must be breps/extrusions/surfaces");

        ON_SimpleArray<ON_Curve*> outCurves;
        ON_3dPointArray outPoints;
        RhinoIntersectBreps(*brep1, *brep2, tol, true, outCurves, &outPoints);

        UndoScope undo(pDoc, L"Intersect breps");

        nlohmann::json curveIds = nlohmann::json::array();
        for (int i = 0; i < outCurves.Count(); ++i)
        {
            if (outCurves[i])
            {
                CRhinoCurveObject* newObj = pDoc->AddCurveObject(*outCurves[i]);
                if (newObj)
                    curveIds.push_back(UuidToString(newObj->Attributes().m_uuid));
                delete outCurves[i];
                outCurves[i] = nullptr;
            }
        }

        nlohmann::json pointsJson = nlohmann::json::array();
        for (int i = 0; i < outPoints.Count(); ++i)
            pointsJson.push_back(Point3dToJson(outPoints[i]));

        WriteResult wr;
        wr.success = true;
        wr.data["curveCount"] = static_cast<int>(curveIds.size());
        wr.data["pointCount"] = outPoints.Count();
        wr.data["curveIds"] = std::move(curveIds);
        wr.data["points"] = std::move(pointsJson);

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /intersect/plane ──────────────────────────────────────

void HandleIntersectPlane(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID brepId;
    try { brepId = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("plane") || !body["plane"].is_object())
    {
        CRookServer::SendError(res, "Missing 'plane' object with 'origin' and 'normal'");
        return;
    }

    ON_3dPoint origin;
    ON_3dVector normal;
    try {
        origin = ParsePoint3d(body["plane"], "origin");
        normal = ParseVector3d(body["plane"], "normal");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, std::string("Invalid plane: ") + ex.what());
        return;
    }

    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, brepId, origin, normal, tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double tol = (tolerance > 0.0) ? tolerance : pDoc->AbsoluteTolerance();

        const CRhinoObject* obj = pDoc->LookupObject(brepId);
        if (!obj)
            throw std::invalid_argument("Brep object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);
        if (!brep)
            throw std::invalid_argument("Object is not a brep/extrusion/surface");

        ON_Plane plane(origin, normal);

        ON_SimpleArray<ON_Curve*> outCurves;
        ON_3dPointArray outPoints;
        RhinoIntersectPlaneBrep(plane, *brep, tol, true, outCurves, &outPoints);

        UndoScope undo(pDoc, L"Intersect plane-brep");

        nlohmann::json curveIds = nlohmann::json::array();
        for (int i = 0; i < outCurves.Count(); ++i)
        {
            if (outCurves[i])
            {
                CRhinoCurveObject* newObj = pDoc->AddCurveObject(*outCurves[i]);
                if (newObj)
                    curveIds.push_back(UuidToString(newObj->Attributes().m_uuid));
                delete outCurves[i];
                outCurves[i] = nullptr;
            }
        }

        nlohmann::json pointsJson = nlohmann::json::array();
        for (int i = 0; i < outPoints.Count(); ++i)
            pointsJson.push_back(Point3dToJson(outPoints[i]));

        WriteResult wr;
        wr.success = true;
        wr.data["curveCount"] = static_cast<int>(curveIds.size());
        wr.data["pointCount"] = outPoints.Count();
        wr.data["curveIds"] = std::move(curveIds);
        wr.data["points"] = std::move(pointsJson);

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
