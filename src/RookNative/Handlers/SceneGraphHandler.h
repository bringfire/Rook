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
void HandleSceneGraphExactAdjacency(const httplib::Request& req, httplib::Response& res);
void HandleOcctProbe(const httplib::Request& req, httplib::Response& res);  // Spike G tracer
void HandleOcctValidateConverter(const httplib::Request& req, httplib::Response& res);  // Task 4 dev route (removed in Task 8)
void HandleOcctValidateAdjacency(const httplib::Request& req, httplib::Response& res);  // Task 6 dev route (removed in Task 8)

} // namespace Handlers
} // namespace Rook
