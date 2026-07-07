#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleDirectorWorkerPlay(const httplib::Request& req, httplib::Response& res);
void HandleDirectorCaptureProbe(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
