// ObjectsHandler.cpp
//
// GET /objects — paginated object listing with layer/type/name filters.

#include "stdafx.h"
#include "Handlers/ObjectsHandler.h"
#include "Infrastructure/LayerHelpers.h"
#include "Models/Snapshots.h"
#include "Models/DocumentHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <algorithm>

namespace Rook {
namespace Handlers {

struct ObjectsResult {
    int totalCount = 0;
    int offset = 0;
    int limit = 100;
    std::vector<ObjectSnapshot> objects;
};

namespace {

constexpr int kMaxHistoryValueId = 1024;
constexpr int kHistoryMissBudget = 32;

struct ObjectHistorySummary
{
    ObjectSnapshot snapshot;
    std::string commandId;
    std::string commandName;
    int historyVersion = 0;
};

std::string RecordTypeToString(ON_HistoryRecord::RECORD_TYPE recordType)
{
    switch (recordType)
    {
    case ON_HistoryRecord::RECORD_TYPE::history_parameters:
        return "history_parameters";
    case ON_HistoryRecord::RECORD_TYPE::feature_parameters:
        return "feature_parameters";
    default:
        return "unknown";
    }
}

nlohmann::json SerializePoint(const ON_3dPoint& point)
{
    return {
        RoundTo(point.x, 4),
        RoundTo(point.y, 4),
        RoundTo(point.z, 4)
    };
}

nlohmann::json SerializeVector(const ON_3dVector& vector)
{
    return {
        RoundTo(vector.x, 4),
        RoundTo(vector.y, 4),
        RoundTo(vector.z, 4)
    };
}

nlohmann::json SerializeXform(const ON_Xform& xform)
{
    nlohmann::json rows = nlohmann::json::array();
    for (int row = 0; row < 4; ++row)
    {
        rows.push_back({
            RoundTo(xform.m_xform[row][0], 6),
            RoundTo(xform.m_xform[row][1], 6),
            RoundTo(xform.m_xform[row][2], 6),
            RoundTo(xform.m_xform[row][3], 6)
        });
    }
    return rows;
}

nlohmann::json SerializeColor(const ON_Color& color)
{
    return {
        {"r", static_cast<int>(color.Red())},
        {"g", static_cast<int>(color.Green())},
        {"b", static_cast<int>(color.Blue())}
    };
}

std::string GeometryValueTypeToString(const ON_Geometry* geometry)
{
    if (!geometry)
        return "Unknown";
    if (ON_Brep::Cast(geometry)) return "Brep";
    if (ON_Extrusion::Cast(geometry)) return "Extrusion";
    if (ON_SubD::Cast(geometry)) return "SubD";
    if (ON_Mesh::Cast(geometry)) return "Mesh";
    if (ON_NurbsCurve::Cast(geometry)) return "NurbsCurve";
    if (ON_PolylineCurve::Cast(geometry)) return "PolylineCurve";
    if (ON_ArcCurve::Cast(geometry)) return "ArcCurve";
    if (ON_LineCurve::Cast(geometry)) return "LineCurve";
    if (ON_Curve::Cast(geometry)) return "Curve";
    if (ON_Surface::Cast(geometry)) return "Surface";
    if (ON_Point::Cast(geometry)) return "Point";
    if (ON_PointCloud::Cast(geometry)) return "PointCloud";
    return "Geometry";
}

nlohmann::json SerializeObjRef(const ON_ObjRef& objRef)
{
    nlohmann::json j;
    j["id"] = UuidToString(objRef.m_uuid);

    if (objRef.m_component_index.m_type != ON_COMPONENT_INDEX::invalid_type)
    {
        j["componentIndex"] = {
            {"type", objRef.m_component_index.m_type},
            {"index", objRef.m_component_index.m_index}
        };
    }

    if (objRef.m_point.IsValid())
        j["point"] = SerializePoint(objRef.m_point);

    return j;
}

nlohmann::json SerializeUuidArray(const ON_SimpleArray<ON_UUID>& uuids)
{
    nlohmann::json arr = nlohmann::json::array();
    for (int i = 0; i < uuids.Count(); ++i)
        arr.push_back(UuidToString(uuids[i]));
    return arr;
}

nlohmann::json SerializeObjRefArray(const ON_ClassArray<ON_ObjRef>& objRefs)
{
    nlohmann::json arr = nlohmann::json::array();
    for (int i = 0; i < objRefs.Count(); ++i)
        arr.push_back(SerializeObjRef(objRefs[i]));
    return arr;
}

template<typename TArray, typename TSerializer>
nlohmann::json SerializeArray(const TArray& values, TSerializer serializer)
{
    nlohmann::json arr = nlohmann::json::array();
    for (int i = 0; i < values.Count(); ++i)
        arr.push_back(serializer(values[i]));
    return arr;
}

bool TrySerializeHistoryValue(
    const ON_HistoryRecord& history,
    int valueId,
    std::string& outType,
    nlohmann::json& outValue)
{
    ON_wString stringValue;
    if (history.GetStringValue(valueId, stringValue))
    {
        outType = "string";
        outValue = WideToUtf8(stringValue);
        return true;
    }

    bool boolValue = false;
    if (history.GetBoolValue(valueId, &boolValue))
    {
        outType = "bool";
        outValue = boolValue;
        return true;
    }

    int intValue = 0;
    if (history.GetIntValue(valueId, &intValue))
    {
        outType = "int";
        outValue = intValue;
        return true;
    }

    double doubleValue = 0.0;
    if (history.GetDoubleValue(valueId, &doubleValue))
    {
        outType = "double";
        outValue = RoundTo(doubleValue, 6);
        return true;
    }

    ON_3dPoint pointValue = ON_3dPoint::Origin;
    if (history.GetPointValue(valueId, pointValue))
    {
        outType = "point";
        outValue = SerializePoint(pointValue);
        return true;
    }

    ON_3dVector vectorValue = ON_3dVector::ZeroVector;
    if (history.GetVectorValue(valueId, vectorValue))
    {
        outType = "vector";
        outValue = SerializeVector(vectorValue);
        return true;
    }

    ON_Xform xformValue = ON_Xform::IdentityTransformation;
    if (history.GetXformValue(valueId, xformValue))
    {
        outType = "xform";
        outValue = SerializeXform(xformValue);
        return true;
    }

    ON_Color colorValue = ON_Color::Black;
    if (history.GetColorValue(valueId, &colorValue))
    {
        outType = "color";
        outValue = SerializeColor(colorValue);
        return true;
    }

    ON_ObjRef objRefValue;
    if (history.GetObjRefValue(valueId, objRefValue))
    {
        outType = "objref";
        outValue = SerializeObjRef(objRefValue);
        return true;
    }

    ON_UUID uuidValue = ON_nil_uuid;
    if (history.GetUuidValue(valueId, &uuidValue))
    {
        outType = "uuid";
        outValue = UuidToString(uuidValue);
        return true;
    }

    const ON_Geometry* geometryValue = nullptr;
    if (history.GetGeometryValue(valueId, geometryValue) && geometryValue)
    {
        outType = "geometry";
        outValue = {
            {"geometryType", GeometryValueTypeToString(geometryValue)}
        };
        return true;
    }

    ON_ClassArray<ON_wString> stringValues;
    if (history.GetStringValues(valueId, stringValues) > 0)
    {
        outType = "string[]";
        outValue = SerializeArray(stringValues, [](const ON_wString& value) {
            return nlohmann::json(WideToUtf8(value));
        });
        return true;
    }

    ON_SimpleArray<bool> boolValues;
    if (history.GetBoolValues(valueId, boolValues) > 0)
    {
        outType = "bool[]";
        outValue = SerializeArray(boolValues, [](bool value) {
            return nlohmann::json(value);
        });
        return true;
    }

    ON_SimpleArray<int> intValues;
    if (history.GetIntValues(valueId, intValues) > 0)
    {
        outType = "int[]";
        outValue = SerializeArray(intValues, [](int value) {
            return nlohmann::json(value);
        });
        return true;
    }

    ON_SimpleArray<double> doubleValues;
    if (history.GetDoubleValues(valueId, doubleValues) > 0)
    {
        outType = "double[]";
        outValue = SerializeArray(doubleValues, [](double value) {
            return nlohmann::json(RoundTo(value, 6));
        });
        return true;
    }

    ON_SimpleArray<ON_3dPoint> pointValues;
    if (history.GetPointValues(valueId, pointValues) > 0)
    {
        outType = "point[]";
        outValue = SerializeArray(pointValues, [](const ON_3dPoint& value) {
            return SerializePoint(value);
        });
        return true;
    }

    ON_SimpleArray<ON_3dVector> vectorValues;
    if (history.GetVectorValues(valueId, vectorValues) > 0)
    {
        outType = "vector[]";
        outValue = SerializeArray(vectorValues, [](const ON_3dVector& value) {
            return SerializeVector(value);
        });
        return true;
    }

    ON_SimpleArray<ON_Xform> xformValues;
    if (history.GetXformValues(valueId, xformValues) > 0)
    {
        outType = "xform[]";
        outValue = SerializeArray(xformValues, [](const ON_Xform& value) {
            return SerializeXform(value);
        });
        return true;
    }

    ON_SimpleArray<ON_Color> colorValues;
    if (history.GetColorValues(valueId, colorValues) > 0)
    {
        outType = "color[]";
        outValue = SerializeArray(colorValues, [](const ON_Color& value) {
            return SerializeColor(value);
        });
        return true;
    }

    ON_ClassArray<ON_ObjRef> objRefValues;
    if (history.GetObjRefValues(valueId, objRefValues) > 0)
    {
        outType = "objref[]";
        outValue = SerializeObjRefArray(objRefValues);
        return true;
    }

    ON_SimpleArray<ON_UUID> uuidValues;
    if (history.GetUuidValues(valueId, uuidValues) > 0)
    {
        outType = "uuid[]";
        outValue = SerializeUuidArray(uuidValues);
        return true;
    }

    ON_SimpleArray<const ON_Geometry*> geometryValues;
    if (history.GetGeometryValues(valueId, geometryValues) > 0)
    {
        outType = "geometry[]";
        outValue = SerializeArray(geometryValues, [](const ON_Geometry* value) {
            return nlohmann::json{
                {"geometryType", GeometryValueTypeToString(value)}
            };
        });
        return true;
    }

    return false;
}

unsigned int ParseDocumentSerialNumber(const httplib::Request& req)
{
    unsigned int docSn = 0;

    if (req.has_param("documentSerialNumber"))
    {
        try { docSn = static_cast<unsigned int>(std::stoul(req.get_param_value("documentSerialNumber"))); }
        catch (...) {}
    }

    if (docSn == 0 && !req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object() && body.contains("documentSerialNumber"))
            docSn = body.value("documentSerialNumber", 0u);
    }

    return docSn;
}

std::string ParseObjectId(const httplib::Request& req)
{
    if (req.matches.size() > 1)
        return req.matches[1].str();

    if (req.has_param("id"))
        return req.get_param_value("id");

    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object() && body.contains("id") && body["id"].is_string())
            return body["id"].get<std::string>();
    }

    return {};
}

std::vector<std::string> CollectHistoryIds(
    const CRhinoHistoryRecord& historyRecord,
    bool antecedents)
{
    ON_SimpleArray<ON_UUID> ids;
    if (antecedents)
        historyRecord.GetAntecedents(ids);
    else
        historyRecord.GetDescendants(ids);

    std::vector<std::string> result;
    result.reserve(ids.Count());
    for (int i = 0; i < ids.Count(); ++i)
        result.push_back(UuidToString(ids[i]));
    return result;
}

} // anonymous namespace

void HandleObjects(const httplib::Request& req, httplib::Response& res)
{
    // Parse parameters from query string (GET requests use params, not body).
    std::string layerFilter, typeFilter, nameFilter;
    int limit = 100;
    int offset = 0;
    unsigned int docSn = 0;

    // httplib provides parsed query params in req.params
    if (req.has_param("layer"))  layerFilter = req.get_param_value("layer");
    if (req.has_param("type"))   typeFilter = req.get_param_value("type");
    if (req.has_param("name"))   nameFilter = req.get_param_value("name");
    if (req.has_param("limit"))
    {
        try { limit = std::stoi(req.get_param_value("limit")); }
        catch (...) {}
    }
    if (req.has_param("offset"))
    {
        try { offset = std::stoi(req.get_param_value("offset")); }
        catch (...) {}
    }
    if (req.has_param("documentSerialNumber"))
    {
        try { docSn = static_cast<unsigned int>(std::stoul(req.get_param_value("documentSerialNumber"))); }
        catch (...) {}
    }

    // Also check JSON body (the C# server converts GET params to body)
    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object())
        {
            if (layerFilter.empty()) layerFilter = body.value("layer", "");
            if (typeFilter.empty())  typeFilter = body.value("type", "");
            if (nameFilter.empty())  nameFilter = body.value("name", "");
            if (body.contains("limit"))  limit = body.value("limit", 100);
            if (body.contains("offset")) offset = body.value("offset", 0);
            if (body.contains("documentSerialNumber"))
                docSn = body.value("documentSerialNumber", 0u);
        }
    }

    limit = (std::max)(1, (std::min)(limit, 500));
    offset = (std::max)(offset, 0);

    // Capture by value into the dispatch lambda
    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [layerFilter, typeFilter, nameFilter, limit, offset, docSn]() -> ObjectsResult
    {
        // Resolve document
        CRhinoDoc* pDoc = nullptr;
        if (docSn > 0)
            pDoc = CRhinoDoc::FromRuntimeSerialNumber(docSn);
        if (!pDoc)
            pDoc = GetDocument();
        if (!pDoc)
            throw std::runtime_error("No active document");

        ObjectsResult result;
        result.offset = offset;
        result.limit = limit;

        // Resolve type filter to bitmask
        unsigned int filterType = ParseObjectTypeFilter(typeFilter);

        // Resolve layer filter to index (-1 = no filter)
        int filterLayerIdx = -1;
        if (!layerFilter.empty())
        {
            filterLayerIdx = Rook::Infrastructure::ResolveLayerRef(
                pDoc, layerFilter, "layer").index;
        }

        // Set up iterator with type filter
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        if (filterType != 0)
            it.SetObjectFilter(filterType);

        // Pre-convert name filter to wide + uppercase (once, outside the loop)
        ON_wString upperNameFilter;
        if (!nameFilter.empty())
        {
            ON_wString wNameFilter;
            int wlen = ::MultiByteToWideChar(CP_UTF8, 0, nameFilter.c_str(), -1, nullptr, 0);
            if (wlen > 0)
            {
                wNameFilter.SetLength(wlen - 1);
                ::MultiByteToWideChar(CP_UTF8, 0, nameFilter.c_str(), -1, wNameFilter.Array(), wlen);
            }
            upperNameFilter = wNameFilter;
            upperNameFilter.MakeUpper();
        }

        // Collect matching object pointers (just pointers — cheap)
        std::vector<const CRhinoObject*> matches;
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            // Layer filter
            if (filterLayerIdx >= 0 && obj->Attributes().m_layer_index != filterLayerIdx)
                continue;

            // Name filter (case-insensitive substring)
            if (!nameFilter.empty())
            {
                ON_wString objName = obj->Attributes().m_name;
                if (objName.IsEmpty())
                    continue;

                ON_wString upperName = objName;
                upperName.MakeUpper();
                if (upperName.Find(static_cast<const wchar_t*>(upperNameFilter)) < 0)
                    continue;
            }

            matches.push_back(obj);
        }

        result.totalCount = static_cast<int>(matches.size());

        // Snapshot only the paginated slice
        int start = (std::min)(offset, result.totalCount);
        int end = (std::min)(start + limit, result.totalCount);
        result.objects.reserve(end - start);

        for (int i = start; i < end; ++i)
            result.objects.push_back(CaptureObjectSnapshot(matches[i], pDoc));

        return result;
    });

    try
    {
        auto result = future.get();

        // Serialize on worker thread
        nlohmann::json objectsArray = nlohmann::json::array();
        for (const auto& obj : result.objects)
            objectsArray.push_back(Serializer::SerializeObject(obj));

        nlohmann::json data;
        data["totalCount"] = result.totalCount;
        data["offset"] = result.offset;
        data["limit"] = result.limit;
        data["count"] = static_cast<int>(result.objects.size());
        data["objects"] = std::move(objectsArray);

        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

void HandleObjectHistory(const httplib::Request& req, httplib::Response& res)
{
    const std::string idStr = ParseObjectId(req);
    if (idStr.empty())
    {
        CRookServer::SendError(res, "Object ID required");
        return;
    }

    const unsigned int docSn = ParseDocumentSerialNumber(req);
    const ON_UUID uuid = ON_UuidFromString(idStr.c_str());
    if (ON_UuidIsNil(uuid))
    {
        CRookServer::SendError(res, "Invalid UUID format: " + idStr);
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [uuid, idStr, docSn]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj)
            throw std::runtime_error("Object not found: " + idStr);

        const CRhinoHistoryRecord* historyRecord = obj->HistoryRecord();
        if (!historyRecord)
            throw std::runtime_error("Object has no history record: " + idStr);

        const ON_HistoryRecord& history = historyRecord->m_hr;
        CRhinoCommand* command = historyRecord->Command();

        nlohmann::json slots = nlohmann::json::array();
        nlohmann::json parameters = nlohmann::json::object();
        int consecutiveMisses = 0;
        for (int valueId = 1; valueId <= kMaxHistoryValueId; ++valueId)
        {
            std::string valueType;
            nlohmann::json valueJson;
            if (!TrySerializeHistoryValue(history, valueId, valueType, valueJson))
            {
                if (++consecutiveMisses >= kHistoryMissBudget)
                    break;
                continue;
            }

            consecutiveMisses = 0;
            nlohmann::json slot;
            slot["valueId"] = valueId;
            slot["type"] = valueType;
            slot["value"] = valueJson;
            slots.push_back(std::move(slot));
            parameters[std::to_string(valueId)] = std::move(valueJson);
        }

        ON_wString valueReportText;
        ON_TextLog valueReport(valueReportText);
        history.ValueReport(valueReport);

        ON_wString reportText;
        ON_TextLog report(reportText);
        historyRecord->Report(report);

        nlohmann::json result;
        result["objectId"] = idStr;
        result["recordId"] = UuidToString(historyRecord->HistoryRecordId());
        result["commandId"] = UuidToString(history.m_command_id);
        result["commandName"] = command ? WideToUtf8(command->EnglishCommandName()) : "";
        result["historyVersion"] = historyRecord->HistoryVersion();
        result["recordType"] = RecordTypeToString(history.m_record_type);
        result["native"] = true;
        result["antecedents"] = CollectHistoryIds(*historyRecord, true);
        result["descendants"] = CollectHistoryIds(*historyRecord, false);
        result["parameters"] = std::move(parameters);
        result["parameterSlots"] = std::move(slots);
        result["valueReport"] = WideToUtf8(valueReportText);
        result["report"] = WideToUtf8(reportText);
        return result;
    });

    try
    {
        CRookServer::SendSuccess(res, future.get());
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

void HandleObjectsWithHistory(const httplib::Request& req, httplib::Response& res)
{
    const unsigned int docSn = ParseDocumentSerialNumber(req);
    int limit = 500;
    int offset = 0;

    if (req.has_param("limit"))
    {
        try { limit = std::stoi(req.get_param_value("limit")); }
        catch (...) {}
    }
    if (req.has_param("offset"))
    {
        try { offset = std::stoi(req.get_param_value("offset")); }
        catch (...) {}
    }

    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object())
        {
            if (body.contains("limit")) limit = body.value("limit", limit);
            if (body.contains("offset")) offset = body.value("offset", offset);
        }
    }

    limit = (std::max)(1, (std::min)(limit, 1000));
    offset = (std::max)(offset, 0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, limit, offset]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        std::vector<ObjectHistorySummary> matches;
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);

        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            const CRhinoHistoryRecord* historyRecord = obj->HistoryRecord();
            if (!historyRecord)
                continue;

            ObjectHistorySummary summary;
            summary.snapshot = CaptureObjectSnapshot(obj, pDoc);
            summary.commandId = UuidToString(historyRecord->m_hr.m_command_id);
            summary.historyVersion = historyRecord->HistoryVersion();

            CRhinoCommand* command = historyRecord->Command();
            if (command)
                summary.commandName = WideToUtf8(command->EnglishCommandName());

            matches.push_back(std::move(summary));
        }

        const int totalCount = static_cast<int>(matches.size());
        const int start = (std::min)(offset, totalCount);
        const int end = (std::min)(start + limit, totalCount);

        nlohmann::json objects = nlohmann::json::array();
        for (int i = start; i < end; ++i)
        {
            nlohmann::json item = Serializer::SerializeObject(matches[i].snapshot);
            item["history"] = {
                {"commandId", matches[i].commandId},
                {"commandName", matches[i].commandName},
                {"historyVersion", matches[i].historyVersion},
                {"native", true}
            };
            objects.push_back(std::move(item));
        }

        nlohmann::json result;
        result["totalCount"] = totalCount;
        result["offset"] = offset;
        result["limit"] = limit;
        result["count"] = end - start;
        result["objects"] = std::move(objects);
        return result;
    });

    try
    {
        CRookServer::SendSuccess(res, future.get());
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
