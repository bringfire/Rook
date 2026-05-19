// CommandHandler.h

#pragma once

#include <mutex>

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleCommand(const httplib::Request& req, httplib::Response& res);
void HandleExecute(const httplib::Request& req, httplib::Response& res);
void HandleRunScriptSafetyTestHook(const httplib::Request& req, httplib::Response& res);
std::unique_lock<std::mutex> AcquireCommandRunLifecycleLock();
void ClearCommandStateUncertain();
bool ConsumeRunScriptSafetyTestHook(const char* hookName);
bool RunScriptSafetyTestHooksEnabled();

} // namespace Handlers
} // namespace Rook
