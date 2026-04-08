// BooleanHandler.h
//
// POST /boolean — Boolean union, difference, intersection, or split

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleBoolean(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
