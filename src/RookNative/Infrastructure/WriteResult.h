// WriteResult.h
//
// Common result struct for write handlers.
// Populated on the main thread, serialized to JSON on the worker thread.

#pragma once

#include <string>

namespace Rook {

struct WriteResult
{
    bool success = true;
    std::string error;
    nlohmann::json data;  // handler-specific payload
};

} // namespace Rook
