#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleDirectorReplay(const httplib::Request& req, httplib::Response& res);
void HandleDirectorReplayCancel(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
