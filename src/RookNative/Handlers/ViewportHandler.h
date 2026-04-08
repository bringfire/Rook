// ViewportHandler.h
//
// POST /viewport — Capture viewport image to file

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleViewport(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
