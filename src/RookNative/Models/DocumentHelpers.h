// DocumentHelpers.h
//
// Header-only utilities shared by all Phase 2+ handlers.
// String conversion, UUID formatting, document resolution, rounding.
// All functions that touch CRhinoDoc must only be called on the main thread.

#pragma once

#include "Threading/RequestContext.h"
#include "Models/Snapshots.h"
#include <string>
#include <unordered_map>
#include <vector>
#include <cmath>

namespace Rook {

// --- String conversion ---

// Convert UTF-8 std::string to ON_wString (UTF-16 on Windows).
// Uses MultiByteToWideChar — the counterpart of WideToUtf8.
inline ON_wString Utf8ToWide(const std::string& utf8)
{
    if (utf8.empty())
        return ON_wString();

    int wlen = ::MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), -1, nullptr, 0);
    if (wlen <= 0)
        return ON_wString();

    ON_wString result;
    result.SetLength(wlen - 1);
    ::MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), -1, result.Array(), wlen);
    return result;
}

// Convert ON_wString (UTF-16 on Windows) to UTF-8 std::string.
// Uses WideCharToMultiByte — never wcstombs (locale-dependent).
inline std::string WideToUtf8(const ON_wString& ws)
{
    if (ws.IsEmpty())
        return {};

    const wchar_t* wstr = static_cast<const wchar_t*>(ws);
    int len = ::WideCharToMultiByte(CP_UTF8, 0, wstr, -1, nullptr, 0, nullptr, nullptr);
    if (len <= 0)
        return {};

    std::string result(static_cast<size_t>(len - 1), '\0');
    ::WideCharToMultiByte(CP_UTF8, 0, wstr, -1, result.data(), len, nullptr, nullptr);
    return result;
}

inline std::string WideToUtf8(const wchar_t* wstr)
{
    if (!wstr || !*wstr)
        return {};

    int len = ::WideCharToMultiByte(CP_UTF8, 0, wstr, -1, nullptr, 0, nullptr, nullptr);
    if (len <= 0)
        return {};

    std::string result(static_cast<size_t>(len - 1), '\0');
    ::WideCharToMultiByte(CP_UTF8, 0, wstr, -1, result.data(), len, nullptr, nullptr);
    return result;
}

// --- UUID ---

// Convert ON_UUID to standard 36-char string "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx".
inline std::string UuidToString(const ON_UUID& uuid)
{
    char buf[64];  // 37 needed; extra headroom for SDK safety
    ON_UuidToString(uuid, buf);
    return std::string(buf);
}

// --- Document resolution ---

// Resolve CRhinoDoc* from the per-request context.
// Checks g_request_doc_serial first, falls back to active document.
// Returns nullptr if no document is available.
// MUST only be called on the main thread (inside a Dispatch lambda).
inline CRhinoDoc* GetDocument()
{
    if (g_request_doc_serial != 0)
    {
        CRhinoDoc* pDoc = CRhinoDoc::FromRuntimeSerialNumber(g_request_doc_serial);
        if (pDoc)
            return pDoc;
    }

    unsigned int sn = CRhinoDoc::TargetDocSerialNumber();
    return CRhinoDoc::FromRuntimeSerialNumber(sn);
}

// Resolve a CRhinoDoc* from an explicit serial number, falling back to GetDocument().
// Throws std::runtime_error if no document is available.
// Shared by all write handlers — avoids duplicate definitions.
inline CRhinoDoc* ResolveDoc(unsigned int docSn)
{
    CRhinoDoc* pDoc = nullptr;
    if (docSn > 0)
        pDoc = CRhinoDoc::FromRuntimeSerialNumber(docSn);
    if (!pDoc)
        pDoc = GetDocument();
    if (!pDoc)
        throw std::runtime_error("No active document");
    return pDoc;
}

// --- Object type mapping ---

// Map ON::object_type enum to the string name used in JSON responses.
// Must match C#'s ObjectType.ToString() exactly.
inline std::string ObjectTypeToString(ON::object_type type)
{
    switch (type)
    {
    case ON::point_object:         return "Point";
    case ON::pointset_object:      return "PointSet";
    case ON::curve_object:         return "Curve";
    case ON::surface_object:       return "Surface";
    case ON::brep_object:          return "Brep";
    case ON::mesh_object:          return "Mesh";
    case ON::light_object:         return "Light";
    case ON::annotation_object:    return "Annotation";
    case ON::instance_reference:   return "InstanceReference";
    case ON::text_dot:             return "TextDot";
    case ON::hatch_object:         return "Hatch";
    case ON::subd_object:          return "SubD";
    case ON::extrusion_object:     return "Extrusion";
    case ON::clipplane_object:     return "ClipPlane";
    case ON::detail_object:        return "Detail";
    default:                       return "Unknown";
    }
}

// The object type names accepted as a `type` filter, with their bitmask.
// Single source for ParseObjectTypeFilter and for the "accepted values" list
// in the error a caller gets for an unrecognized type, so the two cannot drift.
//
// Every name ObjectTypeToString can print for a document object is here, so a
// type read from a listing can be passed back as a filter. "Light" matches
// only when the query includes lights (GET /objects with includeHidden); a
// default query reports the lights it left out in unlistedCount.
struct ObjectTypeFilterEntry
{
    const char* name;
    unsigned int type;
};

inline const std::vector<ObjectTypeFilterEntry>& ObjectTypeFilterEntries()
{
    static const std::vector<ObjectTypeFilterEntry> entries = {
        {"Point",             ON::point_object},
        {"PointSet",          ON::pointset_object},
        {"Curve",             ON::curve_object},
        {"Surface",           ON::surface_object},
        {"Brep",              ON::brep_object},
        {"Mesh",              ON::mesh_object},
        {"Light",             ON::light_object},
        {"Annotation",        ON::annotation_object},
        {"InstanceReference", ON::instance_reference},
        {"TextDot",           ON::text_dot},
        {"Hatch",             ON::hatch_object},
        {"SubD",              ON::subd_object},
        {"Extrusion",         ON::extrusion_object},
        {"ClipPlane",         ON::clipplane_object},
        {"Detail",            ON::detail_object},
    };
    return entries;
}

// "Point, PointSet, Curve, ..." — for error messages.
inline std::string ObjectTypeFilterNames()
{
    std::string names;
    for (const auto& entry : ObjectTypeFilterEntries())
    {
        if (!names.empty()) names += ", ";
        names += entry.name;
    }
    return names;
}

// Parse a type filter string (e.g. "Brep") to ON::object_type bitmask.
// Returns 0 if typeStr is empty (no filter requested) OR unrecognized.
// A caller that received a non-empty typeStr must treat 0 as an error:
// 0 handed to an object iterator means "no filter", i.e. every object.
// Case-insensitive.
inline unsigned int ParseObjectTypeFilter(const std::string& typeStr)
{
    if (typeStr.empty())
        return 0;

    auto iequals = [](const std::string& a, const std::string& b) {
        if (a.size() != b.size()) return false;
        for (size_t i = 0; i < a.size(); ++i)
            if (std::tolower(static_cast<unsigned char>(a[i])) !=
                std::tolower(static_cast<unsigned char>(b[i])))
                return false;
        return true;
    };

    for (const auto& entry : ObjectTypeFilterEntries())
    {
        if (iequals(typeStr, entry.name))
            return entry.type;
    }

    return 0;
}

// --- Object counts ---

// Two object sets are in use, and a count must say which one it is:
//
//   listed — what the default CRhinoObjectIterator returns
//            (normal_or_locked_objects, lights excluded): normal and locked
//            objects on layers that are turned on. GET /objects lists this set
//            unless includeHidden is passed.
//   all    — every undeleted object: the listed set plus objects in hidden
//            mode, objects on a turned-off layer (Rhino's iterator treats
//            those as hidden) and lights. This is the set that holds a layer
//            (rhino_layer_dependencies.directObjects).
//
// objectCount in GET /layers and GET /document is `all`; unlistedObjectCount
// is `all - listed`, so the two sets stay reconcilable from one response.
// Objects in the deleted state (kept for undo) are in neither. Nor are the
// two kinds no pass here iterates: geometry inside block definitions (the
// instance references are counted, the definition's members are not) and
// worksession reference objects (both passes use active_objects). A layer
// used only by block-definition geometry therefore counts 0;
// rhino_layer_dependencies reports that use separately, as blockReferences.
struct ObjectCounts
{
    int all = 0;
    int listed = 0;

    int Unlisted() const { return all - listed; }
};

// Count the objects on one layer, or in the whole document when layerIndex
// is negative. MUST only be called on the main thread.
inline ObjectCounts CountObjects(CRhinoDoc* pDoc, int layerIndex = -1)
{
    ObjectCounts counts;
    {
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::undeleted_objects,
            CRhinoObjectIterator::active_objects);
        it.IncludeLights(true);
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            if (layerIndex < 0 || obj->Attributes().m_layer_index == layerIndex)
                ++counts.all;
        }
    }
    {
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            if (layerIndex < 0 || obj->Attributes().m_layer_index == layerIndex)
                ++counts.listed;
        }
    }
    return counts;
}

// The same two counts for every layer in one pass each, keyed by layer index.
// MUST only be called on the main thread.
inline std::unordered_map<int, ObjectCounts> CountObjectsByLayer(CRhinoDoc* pDoc)
{
    std::unordered_map<int, ObjectCounts> perLayer;
    {
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::undeleted_objects,
            CRhinoObjectIterator::active_objects);
        it.IncludeLights(true);
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            ++perLayer[obj->Attributes().m_layer_index].all;
    }
    {
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            ++perLayer[obj->Attributes().m_layer_index].listed;
    }
    return perLayer;
}

// --- Rounding ---

// Round a double to N decimal places. Coordinates → 4, angles → 2.
// Returns 0.0 for NaN/Inf to prevent invalid JSON output.
inline double RoundTo(double value, int decimals)
{
    if (!std::isfinite(value))
        return 0.0;
    double factor = std::pow(10.0, decimals);
    return std::round(value * factor) / factor;
}

// --- Layer lookup ---

// Find a layer by full path first, then by case-insensitive name.
// Returns layer index or -1 if not found.
// MUST only be called on the main thread.
inline int FindLayerIndex(CRhinoDoc* pDoc, const std::string& name)
{
    ON_wString wName = Utf8ToWide(name);

    int idx = pDoc->m_layer_table.FindLayerFromFullPathName(
        static_cast<const wchar_t*>(wName), -1);
    if (idx >= 0)
        return idx;

    for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
    {
        const CRhinoLayer& layer = pDoc->m_layer_table[i];
        if (layer.IsDeleted())
            continue;
        if (layer.Name().CompareNoCase(wName) == 0)
            return i;
    }

    return -1;
}

// --- Object snapshot capture ---

// Capture an ObjectSnapshot from a CRhinoObject on the main thread.
// Shared by ObjectsHandler (GET /objects) and SelectionHandler (GET /selection).
// Requires Snapshots.h to be included by the calling .cpp file.
inline ObjectSnapshot CaptureObjectSnapshot(const CRhinoObject* obj, CRhinoDoc* pDoc)
{
    ObjectSnapshot snap;
    snap.id = UuidToString(obj->Attributes().m_uuid);
    snap.type = ObjectTypeToString(obj->ObjectType());

    int layerIdx = obj->Attributes().m_layer_index;
    if (layerIdx >= 0 && layerIdx < pDoc->m_layer_table.LayerCount())
    {
        ON_wString layerPath;
        pDoc->m_layer_table.GetLayerPathName(layerIdx, layerPath);
        snap.layer = WideToUtf8(layerPath);
    }
    else
    {
        snap.layer = "Default";
    }

    snap.name = WideToUtf8(obj->Attributes().m_name);
    snap.visible = obj->IsVisible();

    ON_BoundingBox bbox = obj->BoundingBox();
    if (bbox.IsValid())
    {
        snap.bbox.min = { RoundTo(bbox.m_min.x, 4), RoundTo(bbox.m_min.y, 4), RoundTo(bbox.m_min.z, 4) };
        snap.bbox.max = { RoundTo(bbox.m_max.x, 4), RoundTo(bbox.m_max.y, 4), RoundTo(bbox.m_max.z, 4) };
    }

    if (obj->Attributes().ColorSource() == ON::color_from_object)
    {
        ON_Color c = obj->Attributes().m_color;
        snap.color = ColorSnapshot{
            static_cast<int>(c.Red()),
            static_cast<int>(c.Green()),
            static_cast<int>(c.Blue())
        };
    }

    return snap;
}

} // namespace Rook
