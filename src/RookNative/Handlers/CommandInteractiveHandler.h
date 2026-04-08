// CommandInteractiveHandler.h
//
// Interactive command endpoints: prompt reading, command start, input, cancel.
// Enables step-by-step command interaction for AI-driven workflows.

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleCommandPrompt(const httplib::Request& req, httplib::Response& res);
void HandleCommandStart(const httplib::Request& req, httplib::Response& res);
void HandleCommandInput(const httplib::Request& req, httplib::Response& res);
void HandleCommandCancel(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
