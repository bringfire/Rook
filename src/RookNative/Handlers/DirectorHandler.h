#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleDirectorObjectStates(const httplib::Request& req, httplib::Response& res);
void HandleDirectorViewState(const httplib::Request& req, httplib::Response& res);
void HandleDirectorCurveSamples(const httplib::Request& req, httplib::Response& res);
void HandleDirectorVideoAssemble(const httplib::Request& req, httplib::Response& res);
void HandleDirectorFrameCapture(const httplib::Request& req, httplib::Response& res);
void HandleDirectorCaptureDepthPass(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
