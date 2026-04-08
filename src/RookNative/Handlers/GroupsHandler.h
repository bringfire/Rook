// GroupsHandler.h
//
// GET  /groups        — List all groups
// POST /group         — Create a group from object IDs
// POST /ungroup       — Delete a group by name or index
// GET  /group/members — Get objects belonging to a group

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleGetGroups(const httplib::Request& req, httplib::Response& res);
void HandleGroup(const httplib::Request& req, httplib::Response& res);
void HandleUngroup(const httplib::Request& req, httplib::Response& res);
void HandleGroupMembers(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
