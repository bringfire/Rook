// SceneGraphHandler.h
//
// Scene graph HTTP endpoint declarations.
// 8 endpoint functions, 9 route registrations (GET+POST for /scene/graph/node).

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleSceneGraph(const httplib::Request& req, httplib::Response& res);
void HandleSceneGraphNode(const httplib::Request& req, httplib::Response& res);
void HandleSceneGraphQuery(const httplib::Request& req, httplib::Response& res);
void HandleSceneGraphStats(const httplib::Request& req, httplib::Response& res);
void HandleSceneGraphDiff(const httplib::Request& req, httplib::Response& res);
void HandleSceneGraphReconcile(const httplib::Request& req, httplib::Response& res);
void HandleSceneGraphClassify(const httplib::Request& req, httplib::Response& res);
void HandleSceneGraphOverlay(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
