// DocumentOpsHandler.h
//
// POST /document/open       — Open an existing .3dm file
// POST /document/save       — Save document to disk
// POST /document/save-copy  — Write a copy without retargeting the document
// POST /document/new        — Create new document
// POST /document/units   — Change model units
// GET  /views            — List named views
// POST /views/save       — Save current viewport as named view
// POST /views/restore    — Restore a named view

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleDocumentOpen(const httplib::Request& req, httplib::Response& res);
void HandleDocumentSave(const httplib::Request& req, httplib::Response& res);
void HandleDocumentSaveCopy(const httplib::Request& req, httplib::Response& res);
void HandleDocumentNew(const httplib::Request& req, httplib::Response& res);
void HandleDocumentUnits(const httplib::Request& req, httplib::Response& res);
void HandleGetViews(const httplib::Request& req, httplib::Response& res);
void HandleViewsSave(const httplib::Request& req, httplib::Response& res);
void HandleViewsRestore(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
