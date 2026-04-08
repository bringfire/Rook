// JsonHelpers.h
//
// Header-only JSON extraction utilities for write handlers.
// Parses points, vectors, UUIDs, and colors from flexible JSON formats
// matching the C# CreateHandler's input conventions.

#pragma once

#include <string>
#include <vector>
#include <stdexcept>
#include "Models/DocumentHelpers.h"  // Utf8ToWide, WideToUtf8, ResolveDoc, etc.

namespace Rook {

// --- Point / Vector parsing ---

// Parse a 3D point from JSON. Accepts:
//   [x, y, z]       — 3-element array
//   [x, y]          — 2-element array (z = 0)
//   { "x": 1, "y": 2, "z": 3 }
// Throws std::invalid_argument on bad input.
inline ON_3dPoint ParsePoint3d(const nlohmann::json& j, const std::string& key)
{
    if (!j.contains(key))
        throw std::invalid_argument("Missing required field: " + key);

    const auto& val = j[key];

    if (val.is_array())
    {
        if (val.size() < 2)
            throw std::invalid_argument(key + " array must have at least 2 elements");
        double x = val[0].get<double>();
        double y = val[1].get<double>();
        double z = (val.size() >= 3) ? val[2].get<double>() : 0.0;
        return ON_3dPoint(x, y, z);
    }

    if (val.is_object())
    {
        double x = val.value("x", 0.0);
        double y = val.value("y", 0.0);
        double z = val.value("z", 0.0);
        return ON_3dPoint(x, y, z);
    }

    throw std::invalid_argument(key + " must be an array [x,y,z] or object {x,y,z}");
}

// Same as ParsePoint3d but returns ON_3dVector.
inline ON_3dVector ParseVector3d(const nlohmann::json& j, const std::string& key)
{
    ON_3dPoint pt = ParsePoint3d(j, key);
    return ON_3dVector(pt.x, pt.y, pt.z);
}

// Parse an optional point, returning a default if the key is absent.
inline ON_3dPoint ParsePoint3dOrDefault(const nlohmann::json& j, const std::string& key,
                                         const ON_3dPoint& defaultVal)
{
    if (!j.contains(key))
        return defaultVal;
    return ParsePoint3d(j, key);
}

// Parse an optional vector, returning a default if the key is absent.
inline ON_3dVector ParseVector3dOrDefault(const nlohmann::json& j, const std::string& key,
                                           const ON_3dVector& defaultVal)
{
    if (!j.contains(key))
        return defaultVal;
    return ParseVector3d(j, key);
}

// --- Point array parsing ---

inline std::vector<ON_3dPoint> ParsePointArray(const nlohmann::json& j, const std::string& key)
{
    if (!j.contains(key) || !j[key].is_array())
        throw std::invalid_argument("Missing or invalid array: " + key);

    const auto& arr = j[key];
    std::vector<ON_3dPoint> points;
    points.reserve(arr.size());

    for (size_t i = 0; i < arr.size(); ++i)
    {
        const auto& pt = arr[i];
        if (pt.is_array())
        {
            if (pt.size() < 2)
                throw std::invalid_argument(key + "[" + std::to_string(i) + "] must have at least 2 elements");
            double x = pt[0].get<double>();
            double y = pt[1].get<double>();
            double z = (pt.size() >= 3) ? pt[2].get<double>() : 0.0;
            points.emplace_back(x, y, z);
        }
        else if (pt.is_object())
        {
            points.emplace_back(pt.value("x", 0.0), pt.value("y", 0.0), pt.value("z", 0.0));
        }
        else
        {
            throw std::invalid_argument(key + "[" + std::to_string(i) + "] must be an array or object");
        }
    }

    return points;
}

// --- UUID parsing ---

inline ON_UUID ParseUuid(const nlohmann::json& j, const std::string& key)
{
    if (!j.contains(key) || !j[key].is_string())
        throw std::invalid_argument("Missing or invalid UUID: " + key);

    std::string str = j[key].get<std::string>();
    // ON_UuidFromString(const char*) returns ON_UUID directly.
    // Returns ON_nil_uuid if the string is invalid.
    ON_UUID uuid = ON_UuidFromString(str.c_str());
    if (ON_UuidIsNil(uuid))
        throw std::invalid_argument("Invalid UUID format: " + str);
    return uuid;
}

inline std::vector<ON_UUID> ParseUuids(const nlohmann::json& j, const std::string& key)
{
    if (!j.contains(key) || !j[key].is_array())
        throw std::invalid_argument("Missing or invalid UUID array: " + key);

    const auto& arr = j[key];
    std::vector<ON_UUID> result;
    result.reserve(arr.size());

    for (size_t i = 0; i < arr.size(); ++i)
    {
        if (!arr[i].is_string())
            throw std::invalid_argument(key + "[" + std::to_string(i) + "] must be a string");

        std::string str = arr[i].get<std::string>();
        ON_UUID uuid = ON_UuidFromString(str.c_str());
        if (ON_UuidIsNil(uuid))
            throw std::invalid_argument("Invalid UUID at " + key + "[" + std::to_string(i) + "]: " + str);
        result.push_back(uuid);
    }

    return result;
}

// --- Color parsing ---

// Accepts: [r,g,b], {r,g,b}, or "#rrggbb"
inline ON_Color ParseColor(const nlohmann::json& j, const std::string& key)
{
    if (!j.contains(key))
        throw std::invalid_argument("Missing color field: " + key);

    const auto& val = j[key];

    if (val.is_array() && val.size() >= 3)
    {
        return ON_Color(
            static_cast<unsigned int>(val[0].get<int>()),
            static_cast<unsigned int>(val[1].get<int>()),
            static_cast<unsigned int>(val[2].get<int>())
        );
    }

    if (val.is_object())
    {
        return ON_Color(
            static_cast<unsigned int>(val.value("r", 0)),
            static_cast<unsigned int>(val.value("g", 0)),
            static_cast<unsigned int>(val.value("b", 0))
        );
    }

    if (val.is_string())
    {
        std::string hex = val.get<std::string>();
        if (hex.size() == 7 && hex[0] == '#')
        {
            unsigned int r = std::stoul(hex.substr(1, 2), nullptr, 16);
            unsigned int g = std::stoul(hex.substr(3, 2), nullptr, 16);
            unsigned int b = std::stoul(hex.substr(5, 2), nullptr, 16);
            return ON_Color(r, g, b);
        }
    }

    throw std::invalid_argument("Invalid color format for " + key);
}

// --- Case-insensitive string comparison ---

inline bool IEquals(const std::string& a, const std::string& b)
{
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i)
    {
        if (std::tolower(static_cast<unsigned char>(a[i])) !=
            std::tolower(static_cast<unsigned char>(b[i])))
            return false;
    }
    return true;
}

// --- Request body parsing ---

// Parse JSON body and optional documentSerialNumber from an HTTP request.
// Shared by all handlers that accept POST bodies.
// Requires httplib::Request (available via stdafx.h which all .cpp files include first).
inline std::pair<unsigned int, nlohmann::json> ParseBodyAndDocSn(const httplib::Request& req)
{
    unsigned int docSn = 0;
    nlohmann::json body = nlohmann::json::object();

    if (!req.body.empty())
    {
        body = nlohmann::json::parse(req.body, nullptr, false);
        if (body.is_discarded() || !body.is_object())
            body = nlohmann::json::object();
    }

    if (body.contains("documentSerialNumber"))
        docSn = body.value("documentSerialNumber", 0u);

    return { docSn, std::move(body) };
}

} // namespace Rook
