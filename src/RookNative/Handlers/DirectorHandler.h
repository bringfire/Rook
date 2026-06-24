#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleDirectorObjectStates(const httplib::Request& req, httplib::Response& res);
void HandleDirectorViewState(const httplib::Request& req, httplib::Response& res);
void HandleDirectorCurveSamples(const httplib::Request& req, httplib::Response& res);
void HandleDirectorVideoAssemble(const httplib::Request& req, httplib::Response& res);
void HandleDirectorFrameCapture(const httplib::Request& req, httplib::Response& res);

// THROWAWAY spike probe — REVERTED in Task 5. Gated by ROOK_DIRECTOR_PUMPSPIKE env flag.
void HandleDirectorPumpSpike(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
