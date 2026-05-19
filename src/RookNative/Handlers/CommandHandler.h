// CommandHandler.h

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleCommand(const httplib::Request& req, httplib::Response& res);
void HandleExecute(const httplib::Request& req, httplib::Response& res);
void ClearCommandStateUncertain();

} // namespace Handlers
} // namespace Rook
