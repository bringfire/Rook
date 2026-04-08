// DocumentHandler.h

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleDocument(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
