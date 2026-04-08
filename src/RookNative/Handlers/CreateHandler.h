// CreateHandler.h

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleCreate(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
