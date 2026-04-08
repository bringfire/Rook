// GameExportHandler.h
//
// POST /game-export/tag              — Tag objects with semantic metadata
// POST /game-export/tag-from-layers  — Batch tag from layer naming
// POST /game-export/validate         — Pre-flight validation checks
// POST /game-export/export           — Export .3dm + JSON manifest
// POST /game-export/prepare          — Orchestrator: tag → validate → export

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleGameExportTag(const httplib::Request& req, httplib::Response& res);
void HandleGameExportTagFromLayers(const httplib::Request& req, httplib::Response& res);
void HandleGameExportValidate(const httplib::Request& req, httplib::Response& res);
void HandleGameExportExport(const httplib::Request& req, httplib::Response& res);
void HandleGameExportPrepare(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
