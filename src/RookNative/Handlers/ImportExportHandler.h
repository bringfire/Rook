// ImportExportHandler.h
//
// POST /import — Import geometry from file
// POST /export — Export geometry to file

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

void HandleImport(const httplib::Request& req, httplib::Response& res);
void HandleReconstructionImport(const httplib::Request& req, httplib::Response& res);
void HandleExport(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
