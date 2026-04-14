// GrasshopperProxyHandler.cpp
//
// Grasshopper routes are executed through a managed callback bridge that is
// registered from Rhino's real managed runtime. The legacy managed HTTP proxy
// remains only for non-GH compatibility paths still being retired.

#include "stdafx.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "RookServer.h"
#include "Threading/MainThreadDispatcher.h"

#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <winhttp.h>

#pragma comment(lib, "winhttp.lib")

namespace fs = std::filesystem;

namespace Rook {
namespace Handlers {

namespace {

ON_3dVector GetMake2dViewDirection(const std::string& viewName)
{
    if (IEquals(viewName, "top")) return -ON_3dVector::ZAxis;
    if (IEquals(viewName, "bottom")) return ON_3dVector::ZAxis;
    if (IEquals(viewName, "front")) return -ON_3dVector::YAxis;
    if (IEquals(viewName, "back")) return ON_3dVector::YAxis;
    if (IEquals(viewName, "left")) return ON_3dVector::XAxis;
    if (IEquals(viewName, "right")) return -ON_3dVector::XAxis;
    if (IEquals(viewName, "perspective")) return ON_3dVector(-1.0, -1.0, -1.0);
    return -ON_3dVector::YAxis;
}

ON_3dVector GetMake2dUpDirection(const std::string& viewName)
{
    if (IEquals(viewName, "top")) return ON_3dVector::YAxis;
    if (IEquals(viewName, "bottom")) return -ON_3dVector::YAxis;
    return ON_3dVector::ZAxis;
}

int EnsureMake2dLayer(CRhinoDoc* pDoc, const std::string& layerName)
{
    int layerIdx = FindLayerIndex(pDoc, layerName);
    if (layerIdx >= 0)
        return layerIdx;

    ON_Layer layer;
    layer.SetName(Utf8ToWide(layerName));
    return pDoc->m_layer_table.AddLayer(layer);
}

int EnsureMake2dHiddenLayer(CRhinoDoc* pDoc, int parentLayerIdx)
{
    if (parentLayerIdx < 0)
        return -1;

    std::string parentName = WideToUtf8(pDoc->m_layer_table[parentLayerIdx].Name());
    const std::string hiddenLayerPath = parentName + "::Hidden";
    int layerIdx = FindLayerIndex(pDoc, hiddenLayerPath);
    if (layerIdx >= 0)
        return layerIdx;

    ON_Layer hiddenLayer;
    hiddenLayer.SetName(L"Hidden");
    hiddenLayer.SetParentLayerId(pDoc->m_layer_table[parentLayerIdx].Id());
    hiddenLayer.SetColor(ON_Color(128, 128, 128));
    return pDoc->m_layer_table.AddLayer(hiddenLayer);
}

constexpr auto kDiscoveryFolderName = "rook";
constexpr uint32_t kGhBridgeAbiVersion = 12;

using GhBridgeCallbackFn = int(__stdcall*)(
    const char* request_json_utf8,
    int32_t request_json_length,
    char* response_json_utf8,
    int32_t response_json_capacity,
    int32_t* response_json_length,
    int32_t* http_status_code);

struct GhBridgeRegistration
{
    uint32_t struct_size = sizeof(GhBridgeRegistration);
    uint32_t version = kGhBridgeAbiVersion;
    GhBridgeCallbackFn gh_status = nullptr;
    GhBridgeCallbackFn gh_document = nullptr;
    GhBridgeCallbackFn gh_query = nullptr;
    GhBridgeCallbackFn gh_selection = nullptr;
    GhBridgeCallbackFn gh_categories = nullptr;
    GhBridgeCallbackFn gh_library = nullptr;
    GhBridgeCallbackFn gh_get_value = nullptr;
    GhBridgeCallbackFn gh_connections = nullptr;
    GhBridgeCallbackFn gh_groups = nullptr;
    GhBridgeCallbackFn gh_component = nullptr;
    GhBridgeCallbackFn gh_inspect_output = nullptr;
    GhBridgeCallbackFn gh_errors = nullptr;
    GhBridgeCallbackFn gh_get_reference = nullptr;
    GhBridgeCallbackFn gh_set_script = nullptr;
    GhBridgeCallbackFn gh_preview = nullptr;
    GhBridgeCallbackFn gh_clear = nullptr;
    GhBridgeCallbackFn gh_open_document = nullptr;
    GhBridgeCallbackFn gh_new_document = nullptr;
    GhBridgeCallbackFn gh_set_reference = nullptr;
    GhBridgeCallbackFn gh_clear_reference = nullptr;
    GhBridgeCallbackFn gh_move = nullptr;
    GhBridgeCallbackFn gh_group = nullptr;
    GhBridgeCallbackFn gh_group_resize = nullptr;
    GhBridgeCallbackFn gh_cluster = nullptr;
    GhBridgeCallbackFn gh_explore_selection = nullptr;
    GhBridgeCallbackFn gh_explore_cluster = nullptr;
    GhBridgeCallbackFn gh_batch_component_info = nullptr;
    GhBridgeCallbackFn gh_create_component = nullptr;
    GhBridgeCallbackFn gh_create_slider = nullptr;
    GhBridgeCallbackFn gh_create_panel = nullptr;
    GhBridgeCallbackFn gh_connect = nullptr;
    GhBridgeCallbackFn gh_disconnect = nullptr;
    GhBridgeCallbackFn gh_set_value = nullptr;
    GhBridgeCallbackFn gh_delete = nullptr;
    GhBridgeCallbackFn gh_solve = nullptr;
    // Canvas Graph Protocol
    GhBridgeCallbackFn gh_snapshot = nullptr;
    GhBridgeCallbackFn gh_edit = nullptr;
    GhBridgeCallbackFn gh_undo = nullptr;
    GhBridgeCallbackFn gh_canvas_focus = nullptr;
    GhBridgeCallbackFn gh_canvas_zoom = nullptr;
    GhBridgeCallbackFn gh_canvas_image = nullptr;
    GhBridgeCallbackFn gh_make2d = nullptr;
    GhBridgeCallbackFn gumball_extrude = nullptr;
    GhBridgeCallbackFn gumball_cut = nullptr;
    GhBridgeCallbackFn gumball_settings = nullptr;
    GhBridgeCallbackFn block_set_layers = nullptr;
    GhBridgeCallbackFn block_set_materials = nullptr;
    GhBridgeCallbackFn block_set_instance_properties = nullptr;
    GhBridgeCallbackFn block_set_instance_visibility = nullptr;
    GhBridgeCallbackFn block_transform_instance = nullptr;
    GhBridgeCallbackFn block_array_instances = nullptr;
    GhBridgeCallbackFn block_set_object_colors = nullptr;
    GhBridgeCallbackFn block_set_object_names = nullptr;
    GhBridgeCallbackFn block_set_object_user_strings = nullptr;
    GhBridgeCallbackFn block_find_instances = nullptr;
    GhBridgeCallbackFn block_user_strings = nullptr;
    GhBridgeCallbackFn block_objects_detailed = nullptr;
    GhBridgeCallbackFn block_replace_object_geometry = nullptr;
    GhBridgeCallbackFn block_transform_object = nullptr;
    GhBridgeCallbackFn create_geometry = nullptr;
    GhBridgeCallbackFn uv_planar = nullptr;
    GhBridgeCallbackFn game_export_prepare = nullptr;
    GhBridgeCallbackFn gh_script_params = nullptr;
    GhBridgeCallbackFn gh_bake_output = nullptr;
    // ABI v8: batch block operations
    GhBridgeCallbackFn block_set_layers_batch = nullptr;
    // ABI v9: more batch block operations
    GhBridgeCallbackFn block_set_materials_batch = nullptr;
    GhBridgeCallbackFn block_set_object_colors_batch = nullptr;
    GhBridgeCallbackFn block_set_object_user_strings_batch = nullptr;
    GhBridgeCallbackFn block_set_object_names_batch = nullptr;
    // ABI v10: batch block-instance transform
    GhBridgeCallbackFn block_transform_instance_batch = nullptr;
    // ABI v11: batch replace-object-geometry
    GhBridgeCallbackFn block_replace_object_geometry_batch = nullptr;
    // ABI v12: batch transform-object
    GhBridgeCallbackFn block_transform_object_batch = nullptr;
};

enum class BridgeInvokeResult
{
    Completed,
    Unavailable,
    Failed,
};

std::mutex g_ghBridgeMutex;
GhBridgeRegistration g_ghBridgeRegistration;

void ProxyManagedRequest(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    bool isPost);

void SendProxyFailure(httplib::Response& res, int status, const std::string& message);

GhBridgeRegistration GetGhBridgeRegistrationSnapshot()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    return g_ghBridgeRegistration;
}

std::string BuildRequestJson(const httplib::Request& req)
{
    if (!req.body.empty())
    {
        return req.body;
    }

    nlohmann::json body = nlohmann::json::object();
    for (const auto& param : req.params)
    {
        body[param.first] = param.second;
    }

    return body.dump();
}

bool HasGhBridgeRegistration()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    const auto& registration = g_ghBridgeRegistration;
    return registration.version == kGhBridgeAbiVersion
        && registration.gh_status != nullptr
        && registration.gh_document != nullptr
        && registration.gh_query != nullptr
        && registration.gh_selection != nullptr
        && registration.gh_categories != nullptr
        && registration.gh_library != nullptr
        && registration.gh_get_value != nullptr
        && registration.gh_connections != nullptr
        && registration.gh_groups != nullptr
        && registration.gh_component != nullptr
        && registration.gh_inspect_output != nullptr
        && registration.gh_errors != nullptr
        && registration.gh_get_reference != nullptr
        && registration.gh_set_script != nullptr
        && registration.gh_preview != nullptr
        && registration.gh_clear != nullptr
        && registration.gh_open_document != nullptr
        && registration.gh_new_document != nullptr
        && registration.gh_set_reference != nullptr
        && registration.gh_clear_reference != nullptr
        && registration.gh_move != nullptr
        && registration.gh_group != nullptr
        && registration.gh_group_resize != nullptr
        && registration.gh_cluster != nullptr
        && registration.gh_explore_selection != nullptr
        && registration.gh_explore_cluster != nullptr
        && registration.gh_batch_component_info != nullptr
        && registration.gh_create_component != nullptr
        && registration.gh_create_slider != nullptr
        && registration.gh_create_panel != nullptr
        && registration.gh_connect != nullptr
        && registration.gh_disconnect != nullptr
        && registration.gh_set_value != nullptr
        && registration.gh_delete != nullptr
        && registration.gh_solve != nullptr
        && registration.gh_bake_output != nullptr;
}

std::string GetManagedDiscoveryPath()
{
    const DWORD pid = ::GetCurrentProcessId();
    const fs::path discoveryFolder = fs::temp_directory_path() / kDiscoveryFolderName;
    const fs::path companionPath = discoveryFolder / ("companion-" + std::to_string(pid) + ".json");
    if (fs::exists(companionPath))
    {
        return companionPath.string();
    }

    return (discoveryFolder / ("instance-" + std::to_string(pid) + ".json")).string();
}

bool TryGetManagedPort(int& port, std::string& host, std::string& error)
{
    try
    {
        const std::string discoveryPath = GetManagedDiscoveryPath();
        if (!fs::exists(discoveryPath))
        {
            error = "Managed Grasshopper bridge is unavailable for this Rhino process. "
                "Expected discovery file at " + discoveryPath + ".";
            return false;
        }

        std::ifstream file(discoveryPath);
        if (!file.is_open())
        {
            error = "Failed to open managed Grasshopper discovery file: " + discoveryPath;
            return false;
        }

        nlohmann::json info;
        file >> info;

        if (!info.contains("port") || !info["port"].is_number_integer())
        {
            error = "Managed Grasshopper discovery file does not contain a valid port.";
            return false;
        }

        port = info["port"].get<int>();
        host = info.value("host", "127.0.0.1");
        return true;
    }
    catch (const std::exception& ex)
    {
        error = ex.what();
        return false;
    }
}

BridgeInvokeResult TryInvokeRegisteredCallback(
    GhBridgeCallbackFn callback,
    const httplib::Request& req,
    httplib::Response& res,
    std::string& error)
{
    if (!callback)
    {
        return BridgeInvokeResult::Unavailable;
    }

    const std::string requestJson = BuildRequestJson(req);
    std::vector<char> responseBuffer(1024 * 1024, '\0');
    int32_t responseLength = 0;
    int32_t statusCode = 0;

    const int rc = callback(
        requestJson.c_str(),
        static_cast<int32_t>(requestJson.size()),
        responseBuffer.data(),
        static_cast<int32_t>(responseBuffer.size()),
        &responseLength,
        &statusCode);

    if (rc != 0)
    {
        std::ostringstream message;
        message << "Managed GH callback invocation failed (" << rc << ").";
        error = message.str();
        return BridgeInvokeResult::Failed;
    }

    if (responseLength < 0 || responseLength > static_cast<int32_t>(responseBuffer.size()))
    {
        error = "Managed GH callback returned an invalid response length.";
        return BridgeInvokeResult::Failed;
    }

    res.status = statusCode == 0 ? 200 : statusCode;
    res.set_content(
        std::string(responseBuffer.data(), responseBuffer.data() + responseLength),
        "application/json");
    return BridgeInvokeResult::Completed;
}

void DispatchGrasshopperRoute(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    GhBridgeCallbackFn callback)
{
    std::string error;
    const auto result = TryInvokeRegisteredCallback(callback, req, res, error);
    if (result == BridgeInvokeResult::Completed)
    {
        res.set_header("X-Rook-Gh-Bridge", "callback");
        return;
    }

    if (result == BridgeInvokeResult::Failed)
    {
        RhinoApp().Print(L"RookNative: GH callback bridge failed for %hs. %hs\n",
            path.c_str(),
            error.c_str());
        SendProxyFailure(res, 500, error);
        res.set_header("X-Rook-Gh-Bridge", "callback");
        return;
    }

    SendProxyFailure(
        res,
        503,
        "Native Grasshopper callback bridge is not registered for this Rhino process.");
    res.set_header("X-Rook-Gh-Bridge", "unavailable");
}

void SendProxyFailure(httplib::Response& res, int status, const std::string& message)
{
    nlohmann::json envelope;
    envelope["success"] = false;
    envelope["data"] = message;

    res.status = status;
    res.set_content(envelope.dump(), "application/json");
}

void CopyManagedResponse(const httplib::Result& result, httplib::Response& res)
{
    if (!result)
    {
        SendProxyFailure(res, 502, "Managed Grasshopper bridge request failed before a response was received.");
        return;
    }

    const auto contentType = result->get_header_value("Content-Type");
    res.set_content(
        result->body,
        contentType.empty() ? "application/json" : contentType.c_str());
    res.status = result->status;
}

std::wstring Utf8ToWide(const std::string& input)
{
    if (input.empty())
    {
        return std::wstring();
    }

    const int size = ::MultiByteToWideChar(CP_UTF8, 0, input.c_str(), -1, nullptr, 0);
    if (size <= 0)
    {
        return std::wstring();
    }

    std::wstring result(size - 1, L'\0');
    ::MultiByteToWideChar(CP_UTF8, 0, input.c_str(), -1, result.data(), size);
    return result;
}

std::string WideToUtf8(const std::wstring& input)
{
    if (input.empty())
    {
        return std::string();
    }

    const int size = ::WideCharToMultiByte(CP_UTF8, 0, input.c_str(), -1, nullptr, 0, nullptr, nullptr);
    if (size <= 0)
    {
        return std::string();
    }

    std::string result(size - 1, '\0');
    ::WideCharToMultiByte(CP_UTF8, 0, input.c_str(), -1, result.data(), size, nullptr, nullptr);
    return result;
}

std::string UrlEncode(const std::string& input)
{
    std::ostringstream encoded;
    encoded.fill('0');
    encoded << std::hex << std::uppercase;

    for (unsigned char ch : input)
    {
        if ((ch >= 'A' && ch <= 'Z') ||
            (ch >= 'a' && ch <= 'z') ||
            (ch >= '0' && ch <= '9') ||
            ch == '-' || ch == '_' || ch == '.' || ch == '~')
        {
            encoded << ch;
        }
        else
        {
            encoded << '%' << std::setw(2) << static_cast<int>(ch);
        }
    }

    return encoded.str();
}

std::string BuildTarget(const std::string& path, const httplib::Request& req, bool isPost)
{
    if (isPost || req.params.empty())
    {
        return path;
    }

    std::ostringstream target;
    target << path << '?';

    bool first = true;
    for (const auto& param : req.params)
    {
        if (!first)
        {
            target << '&';
        }

        first = false;
        target << UrlEncode(param.first) << '=' << UrlEncode(param.second);
    }

    return target.str();
}

std::string FormatWinHttpError(const char* step, DWORD errorCode)
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
        {
            text.pop_back();
        }

        const auto utf8 = WideToUtf8(text);
        if (!utf8.empty())
        {
            message << ": " << utf8;
        }
    }

    return message.str();
}

bool QueryResponseHeaderString(HINTERNET request, DWORD infoLevel, std::string& value)
{
    DWORD size = 0;
    if (::WinHttpQueryHeaders(request, infoLevel, WINHTTP_HEADER_NAME_BY_INDEX, nullptr, &size, WINHTTP_NO_HEADER_INDEX))
    {
        return false;
    }

    const DWORD error = ::GetLastError();
    if (error != ERROR_INSUFFICIENT_BUFFER || size == 0)
    {
        return false;
    }

    std::wstring buffer(size / sizeof(wchar_t), L'\0');
    if (!::WinHttpQueryHeaders(
        request,
        infoLevel,
        WINHTTP_HEADER_NAME_BY_INDEX,
        buffer.data(),
        &size,
        WINHTTP_NO_HEADER_INDEX))
    {
        return false;
    }

    if (!buffer.empty() && buffer.back() == L'\0')
    {
        buffer.pop_back();
    }

    value = WideToUtf8(buffer);
    return true;
}

bool QueryResponseStatusCode(HINTERNET request, int& statusCode)
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

bool TryForwardGrasshopperRequest(
    int managedPort,
    const std::string& managedHost,
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    bool isPost,
    std::string& error)
{
    const std::wstring target = Utf8ToWide(BuildTarget(path, req, isPost));
    if (target.empty())
    {
        error = "Failed to build proxied Grasshopper target URL.";
        return false;
    }

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

    const std::wstring wideHost = Utf8ToWide(managedHost);
    if (wideHost.empty())
    {
        error = "Failed to convert managed plugin host to wide string.";
        closeHandles();
        return false;
    }
    connection = ::WinHttpConnect(session, wideHost.c_str(), static_cast<INTERNET_PORT>(managedPort), 0);
    if (!connection)
    {
        error = FormatWinHttpError("WinHttpConnect", ::GetLastError());
        closeHandles();
        return false;
    }

    request = ::WinHttpOpenRequest(
        connection,
        isPost ? L"POST" : L"GET",
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

    std::wstring headerBlock = L"Accept: application/json\r\n";
    if (isPost)
    {
        const auto contentType = req.get_header_value("Content-Type");
        headerBlock += L"Content-Type: ";
        headerBlock += Utf8ToWide(contentType.empty() ? "application/json" : contentType);
        headerBlock += L"\r\n";
    }

    LPVOID optionalBody = WINHTTP_NO_REQUEST_DATA;
    DWORD optionalBodyLength = 0;
    if (isPost && !req.body.empty())
    {
        optionalBody = const_cast<char*>(req.body.data());
        optionalBodyLength = static_cast<DWORD>(req.body.size());
    }

    if (!::WinHttpSendRequest(
        request,
        headerBlock.c_str(),
        static_cast<DWORD>(headerBlock.length()),
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

    int statusCode = 0;
    if (!QueryResponseStatusCode(request, statusCode))
    {
        error = FormatWinHttpError("WinHttpQueryHeaders(status)", ::GetLastError());
        closeHandles();
        return false;
    }

    std::string contentType;
    QueryResponseHeaderString(request, WINHTTP_QUERY_CONTENT_TYPE, contentType);

    std::string responseBody;
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
        {
            break;
        }

        std::string chunk(available, '\0');
        DWORD downloaded = 0;
        if (!::WinHttpReadData(request, chunk.data(), available, &downloaded))
        {
            error = FormatWinHttpError("WinHttpReadData", ::GetLastError());
            closeHandles();
            return false;
        }

        chunk.resize(downloaded);
        responseBody += chunk;
    }

    res.status = statusCode;
    res.set_content(responseBody, contentType.empty() ? "application/json" : contentType.c_str());
    closeHandles();
    return true;
}

void ProxyManagedRequest(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    bool isPost)
{
    int managedPort = 0;
    std::string managedHost = "127.0.0.1";
    std::string error;
    if (!TryGetManagedPort(managedPort, managedHost, error))
    {
        SendProxyFailure(res, 503, error);
        return;
    }

    if (!TryForwardGrasshopperRequest(managedPort, managedHost, req, res, path, isPost, error))
    {
        SendProxyFailure(res, 502, error);
    }
}

} // namespace

extern "C" __declspec(dllexport) int __stdcall RookRegisterGhBridge(const GhBridgeRegistration* registration)
{
    if (registration == nullptr)
    {
        return 1;
    }

    if (registration->version != kGhBridgeAbiVersion)
    {
        return 2;
    }

    if (registration->struct_size < sizeof(GhBridgeRegistration))
    {
        return 3;
    }

    {
        std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
        g_ghBridgeRegistration = *registration;
    }
    CRookServer::Instance().RefreshDiscoveryFile();
    return 0;
}

extern "C" __declspec(dllexport) void __stdcall RookClearGhBridge()
{
    {
        std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
        g_ghBridgeRegistration = GhBridgeRegistration{};
    }
    CRookServer::Instance().RefreshDiscoveryFile();
}

void ClearGrasshopperBridgeRegistration()
{
    RookClearGhBridge();
}

bool HasGrasshopperBridgeRegistration()
{
    return HasGhBridgeRegistration();
}

bool HasCanvasGraphProtocol()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    return g_ghBridgeRegistration.gh_snapshot != nullptr
        && g_ghBridgeRegistration.gh_edit != nullptr
        && g_ghBridgeRegistration.gh_undo != nullptr;
}

bool HasCanvasGraphNavigation()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    return g_ghBridgeRegistration.gh_canvas_focus != nullptr
        && g_ghBridgeRegistration.gh_canvas_zoom != nullptr
        && g_ghBridgeRegistration.gh_canvas_image != nullptr;
}

void DispatchManagedCompanionRouteOrProxy(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    GhBridgeCallbackFn callback,
    bool isPost)
{
    if (callback != nullptr)
    {
        DispatchGrasshopperRoute(req, res, path, callback);
        return;
    }

    ProxyManagedRequest(req, res, path, isPost);
}

void ProxyManagedCompanionRequest(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    bool isPost)
{
    ProxyManagedRequest(req, res, path, isPost);
}

bool TryHandleManagedCreate(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    if (registration.create_geometry != nullptr)
    {
        DispatchGrasshopperRoute(req, res, "/create", registration.create_geometry);
        return true;
    }

    return false;
}

void HandleManagedUvPlanar(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/material/uv-planar", registration.uv_planar, true);
}

void HandleManagedGameExportPrepare(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/game-export/prepare", registration.game_export_prepare, true);
}

void HandleMake2d(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string viewName = body.value("view", std::string("Front"));
    bool showHiddenLines = body.value("showHiddenLines", false);
    std::string targetLayer = body.value("targetLayer", std::string("Make2D"));

    std::vector<ON_UUID> ids;
    if (body.contains("ids"))
    {
        try { ids = ParseUuids(body, "ids"); }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendError(res, ex.what());
            return;
        }
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, viewName, showHiddenLines, targetLayer, ids]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        if (nullptr == pDoc)
            throw std::runtime_error("No active document");

        std::vector<const CRhinoObject*> sourceObjects;
        if (!ids.empty())
        {
            for (const auto& id : ids)
            {
                const CRhinoObject* obj = pDoc->LookupObject(id);
                if (obj && !obj->Attributes().IsInstanceDefinitionObject())
                    sourceObjects.push_back(obj);
            }
        }
        else
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (!obj->Attributes().IsInstanceDefinitionObject())
                    sourceObjects.push_back(obj);
            }
        }

        if (sourceObjects.empty())
            throw std::invalid_argument("No objects to process");

        const int layerIdx = EnsureMake2dLayer(pDoc, targetLayer);
        if (layerIdx < 0)
            throw std::runtime_error("Failed to create target layer");

        int hiddenLayerIdx = -1;
        if (showHiddenLines)
            hiddenLayerIdx = EnsureMake2dHiddenLayer(pDoc, layerIdx);

        const ON_3dVector viewDirection = GetMake2dViewDirection(viewName);
        ON_Plane projectionPlane(ON_3dPoint::Origin, viewDirection);
        ON_Xform toWorldXY;
        if (!toWorldXY.ChangeBasis(projectionPlane, ON_Plane::World_xy))
            throw std::runtime_error("Failed to create Make2D projection transform");

        ON_SilhouetteParameters silhouetteParams;
        if (!silhouetteParams.SetParallel(viewDirection, pDoc->AbsoluteTolerance(), pDoc->AngleToleranceRadians()))
            throw std::runtime_error("Failed to initialize Make2D silhouette parameters");
        silhouetteParams.SetTypeMask(ON_SIL_EVENT::TYPE::kSilBoundary | ON_SIL_EVENT::TYPE::kNonSilCrease);

        UndoScope undo(pDoc, L"Make2D");
        std::vector<std::string> createdIds;
        int visibleCurves = 0;
        int hiddenCurves = 0;

        ON_3dmObjectAttributes visibleAttrs;
        visibleAttrs.m_layer_index = layerIdx;
        ON_3dmObjectAttributes hiddenAttrs;
        hiddenAttrs.m_layer_index = hiddenLayerIdx >= 0 ? hiddenLayerIdx : layerIdx;

        auto addProjectedCurve = [&](const ON_Curve& sourceCurve, bool isHidden) -> void
        {
            std::unique_ptr<ON_Curve> projected(RhinoProjectToPlane(sourceCurve, projectionPlane, pDoc->AbsoluteTolerance()));
            if (!projected)
                return;

            if (!projected->Transform(toWorldXY))
                return;

            const ON_3dmObjectAttributes& attrs = isHidden ? hiddenAttrs : visibleAttrs;
            CRhinoCurveObject* newObj = pDoc->AddCurveObject(*projected, &attrs);
            if (nullptr == newObj)
                return;

            createdIds.push_back(UuidToString(newObj->Id()));
            if (isHidden)
                hiddenCurves++;
            else
                visibleCurves++;
        };

        int supportedCount = 0;
        for (const auto* obj : sourceObjects)
        {
            const ON_Geometry* geometry = obj->Geometry();
            if (nullptr == geometry)
                continue;

            if (const ON_Brep* brep = ON_Brep::Cast(geometry))
            {
                ON_ClassArray<ON_SIL_EVENT> silhouettes;
                if (brep->GetSilhouette(silhouetteParams, nullptr, 0, silhouettes, nullptr, nullptr))
                {
                    for (int i = 0; i < silhouettes.Count(); ++i)
                    {
                        const ON_SIL_EVENT& sil = silhouettes[i];
                        if (sil.m_curve3d != nullptr)
                            addProjectedCurve(*sil.m_curve3d, false);
                    }
                }

                for (int ei = 0; ei < brep->m_E.Count(); ++ei)
                {
                    const ON_BrepEdge& edge = brep->m_E[ei];
                    std::unique_ptr<ON_Curve> edgeCurve(edge.DuplicateCurve());
                    if (edgeCurve)
                        addProjectedCurve(*edgeCurve, false);
                }

                supportedCount++;
                continue;
            }

            if (const ON_Extrusion* extrusion = ON_Extrusion::Cast(geometry))
            {
                std::unique_ptr<ON_Brep> brep(extrusion->BrepForm());
                if (!brep)
                    continue;

                ON_ClassArray<ON_SIL_EVENT> silhouettes;
                if (brep->GetSilhouette(silhouetteParams, nullptr, 0, silhouettes, nullptr, nullptr))
                {
                    for (int i = 0; i < silhouettes.Count(); ++i)
                    {
                        const ON_SIL_EVENT& sil = silhouettes[i];
                        if (sil.m_curve3d != nullptr)
                            addProjectedCurve(*sil.m_curve3d, false);
                    }
                }

                for (int ei = 0; ei < brep->m_E.Count(); ++ei)
                {
                    const ON_BrepEdge& edge = brep->m_E[ei];
                    std::unique_ptr<ON_Curve> edgeCurve(edge.DuplicateCurve());
                    if (edgeCurve)
                        addProjectedCurve(*edgeCurve, false);
                }

                supportedCount++;
                continue;
            }

            if (const ON_Mesh* mesh = ON_Mesh::Cast(geometry))
            {
                ON_ClassArray<ON_SIL_EVENT> silhouettes;
                if (mesh->GetSilhouette(silhouetteParams, nullptr, 0, silhouettes, nullptr, nullptr))
                {
                    for (int i = 0; i < silhouettes.Count(); ++i)
                    {
                        const ON_SIL_EVENT& sil = silhouettes[i];
                        if (sil.m_curve3d != nullptr)
                            addProjectedCurve(*sil.m_curve3d, false);
                    }
                }

                supportedCount++;
                continue;
            }

            if (const ON_Curve* curve = ON_Curve::Cast(geometry))
            {
                addProjectedCurve(*curve, false);
                supportedCount++;
                continue;
            }
        }

        if (supportedCount == 0)
            throw std::invalid_argument("No supported objects to process");

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["view"] = viewName;
        wr.data["visibleCurves"] = visibleCurves;
        wr.data["hiddenCurves"] = hiddenCurves;
        wr.data["createdIds"] = createdIds;
        wr.data["targetLayer"] = targetLayer;
        return wr;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result.data);
        res.set_header("X-Rook-Make2d-Bridge", "native");
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
        res.set_header("X-Rook-Make2d-Bridge", "native");
    }
}

void HandleGrasshopperStatus(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/status", registration.gh_status);
}

void HandleGrasshopperDocument(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/document", registration.gh_document);
}

void HandleGrasshopperQuery(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/query", registration.gh_query);
}

void HandleGrasshopperSelection(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/selection", registration.gh_selection);
}

void HandleGrasshopperCategories(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/categories", registration.gh_categories);
}

void HandleGrasshopperLibrary(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/library", registration.gh_library);
}

void HandleGrasshopperGetValue(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/value", registration.gh_get_value);
}

void HandleGrasshopperSetValue(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/value", registration.gh_set_value);
}

void HandleGrasshopperSetScript(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/script", registration.gh_set_script);
}

void HandleGrasshopperScriptParams(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/script-params", registration.gh_script_params);
}

void HandleGrasshopperConnections(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/connections", registration.gh_connections);
}

void HandleGrasshopperDelete(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/delete", registration.gh_delete);
}

void HandleGrasshopperPreview(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/preview", registration.gh_preview);
}

void HandleGrasshopperClear(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/clear", registration.gh_clear);
}

void HandleGrasshopperOpenDocument(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/document/open", registration.gh_open_document);
}

void HandleGrasshopperNewDocument(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/document/new", registration.gh_new_document);
}

void HandleGrasshopperMove(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/move", registration.gh_move);
}

void HandleGrasshopperGroup(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/group", registration.gh_group);
}

void HandleGrasshopperGroups(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/groups", registration.gh_groups);
}

void HandleGrasshopperGroupResize(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/group-resize", registration.gh_group_resize);
}

void HandleGrasshopperCluster(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/cluster", registration.gh_cluster);
}

void HandleGrasshopperExploreSelection(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/explore-selection", registration.gh_explore_selection);
}

void HandleGrasshopperExploreCluster(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/explore-cluster", registration.gh_explore_cluster);
}

void HandleGrasshopperBatchComponentInfo(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/batch-component-info", registration.gh_batch_component_info);
}

void HandleGrasshopperCreateComponent(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/create-component", registration.gh_create_component);
}

void HandleGrasshopperCreateSlider(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/create-slider", registration.gh_create_slider);
}

void HandleGrasshopperCreatePanel(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/create-panel", registration.gh_create_panel);
}

void HandleGrasshopperComponent(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/component", registration.gh_component);
}

void HandleGrasshopperInspectOutput(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/inspect-output", registration.gh_inspect_output);
}

void HandleGrasshopperErrors(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/errors", registration.gh_errors);
}

void HandleGrasshopperConnect(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/connect", registration.gh_connect);
}

void HandleGrasshopperDisconnect(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/disconnect", registration.gh_disconnect);
}

void HandleGrasshopperSetReference(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/set-reference", registration.gh_set_reference);
}

void HandleGrasshopperGetReference(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/get-reference", registration.gh_get_reference);
}

void HandleGrasshopperClearReference(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/clear-reference", registration.gh_clear_reference);
}

void HandleGrasshopperSolve(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/solve", registration.gh_solve);
}

void HandleGrasshopperSnapshot(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/snapshot", registration.gh_snapshot);
}

void HandleGrasshopperEdit(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/edit", registration.gh_edit);
}

void HandleGrasshopperUndo(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/undo", registration.gh_undo);
}

void HandleGrasshopperCanvasFocus(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/canvas/focus", registration.gh_canvas_focus);
}

void HandleGrasshopperCanvasZoom(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/canvas/zoom", registration.gh_canvas_zoom);
}

void HandleGrasshopperCanvasImage(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/canvas/image", registration.gh_canvas_image);
}

void HandleGrasshopperBakeOutput(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchGrasshopperRoute(req, res, "/gh/bake", registration.gh_bake_output);
}

void HandleManagedBlockSetLayers(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-layers", registration.block_set_layers, true);
}

void HandleManagedBlockSetLayersBatch(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-layers-batch", registration.block_set_layers_batch, true);
}

void HandleManagedBlockSetMaterials(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-materials", registration.block_set_materials, true);
}

void HandleManagedBlockSetMaterialsBatch(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-materials-batch", registration.block_set_materials_batch, true);
}

void HandleManagedBlockSetObjectColors(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-object-colors", registration.block_set_object_colors, true);
}

void HandleManagedBlockSetObjectColorsBatch(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-object-colors-batch", registration.block_set_object_colors_batch, true);
}

void HandleManagedBlockSetObjectNames(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-object-names", registration.block_set_object_names, true);
}

void HandleManagedBlockSetObjectNamesBatch(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-object-names-batch", registration.block_set_object_names_batch, true);
}

void HandleManagedBlockSetObjectUserStringsBatch(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-object-user-strings-batch", registration.block_set_object_user_strings_batch, true);
}

void HandleManagedBlockTransformInstanceBatch(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/transform-instance-batch", registration.block_transform_instance_batch, true);
}

void HandleManagedBlockSetObjectUserStrings(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/set-object-user-strings", registration.block_set_object_user_strings, true);
}

void HandleManagedBlockReplaceObjectGeometry(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/replace-object-geometry", registration.block_replace_object_geometry, true);
}

void HandleManagedBlockReplaceObjectGeometryBatch(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/replace-object-geometry-batch", registration.block_replace_object_geometry_batch, true);
}

void HandleManagedBlockTransformObjectBatch(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/transform-object-batch", registration.block_transform_object_batch, true);
}

void HandleManagedBlockTransformObject(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    DispatchManagedCompanionRouteOrProxy(req, res, "/block/transform-object", registration.block_transform_object, true);
}

} // namespace Handlers
} // namespace Rook
