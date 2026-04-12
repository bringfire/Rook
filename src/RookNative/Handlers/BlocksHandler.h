// BlocksHandler.h
//
// Block definition and instance operations (23 routes, 20 unique handlers).
// GET  /blocks                  — List all block definitions
// POST /block/create            — Create block from objects
// POST /block/insert            — Insert block instance
// POST /block/explode           — Explode instance to objects
// DELETE /block                 — Delete block definition
// POST /block/rename            — Rename block definition
// POST /block/description       — Set description/url metadata
// GET+POST /block/info          — Get block details
// POST /block/add-objects       — Add objects to block
// POST /block/remove-objects    — Remove objects from block
// POST /block/replace-geometry  — Replace block geometry
// GET+POST /block/instances     — List instances with transforms
// POST /block/replace-instance  — Swap to different block
// POST /block/reset-scale       — Normalize instance scale
// POST /block/link              — Link to external file
// POST /block/refresh           — Refresh linked block
// POST /block/unlink            — Unlink from file
// POST /block/purge             — Delete unused definitions
// POST /block/duplicate         — Duplicate definition
// POST /block/rebase            — Rebase definition geometry, compensate instances
// POST /block/rebase-recursive  — Rebase leaf definition, compensate parent defs + direct instances
// GET+POST /block/nested        — Get nested hierarchy

#pragma once

namespace httplib { struct Request; struct Response; }

namespace Rook {
namespace Handlers {

// Core operations
void HandleGetBlocks(const httplib::Request& req, httplib::Response& res);
void HandleBlockCreate(const httplib::Request& req, httplib::Response& res);
void HandleBlockInsert(const httplib::Request& req, httplib::Response& res);
void HandleBlockExplode(const httplib::Request& req, httplib::Response& res);
void HandleBlockDelete(const httplib::Request& req, httplib::Response& res);

// Modification
void HandleBlockRename(const httplib::Request& req, httplib::Response& res);
void HandleBlockDescription(const httplib::Request& req, httplib::Response& res);
void HandleBlockInfo(const httplib::Request& req, httplib::Response& res);

// Geometry management
void HandleBlockAddObjects(const httplib::Request& req, httplib::Response& res);
void HandleBlockRemoveObjects(const httplib::Request& req, httplib::Response& res);
void HandleBlockReplaceGeometry(const httplib::Request& req, httplib::Response& res);

// Instance operations
void HandleBlockInstances(const httplib::Request& req, httplib::Response& res);
void HandleBlockReplaceInstance(const httplib::Request& req, httplib::Response& res);
void HandleBlockResetScale(const httplib::Request& req, httplib::Response& res);
void HandleBlockSetInstanceProperties(const httplib::Request& req, httplib::Response& res);
void HandleBlockSetInstanceVisibility(const httplib::Request& req, httplib::Response& res);
void HandleBlockTransformInstance(const httplib::Request& req, httplib::Response& res);
void HandleBlockArrayInstances(const httplib::Request& req, httplib::Response& res);
void HandleBlockFindInstances(const httplib::Request& req, httplib::Response& res);
void HandleBlockUserStrings(const httplib::Request& req, httplib::Response& res);
void HandleBlockObjectsDetailed(const httplib::Request& req, httplib::Response& res);
void HandleBlockSetLayers(const httplib::Request& req, httplib::Response& res);
void HandleBlockSetMaterials(const httplib::Request& req, httplib::Response& res);
void HandleBlockSetObjectColors(const httplib::Request& req, httplib::Response& res);
void HandleBlockSetObjectNames(const httplib::Request& req, httplib::Response& res);
void HandleBlockSetObjectUserStrings(const httplib::Request& req, httplib::Response& res);

// Linked blocks
void HandleBlockLink(const httplib::Request& req, httplib::Response& res);
void HandleBlockRefresh(const httplib::Request& req, httplib::Response& res);
void HandleBlockUnlink(const httplib::Request& req, httplib::Response& res);

// Utility
void HandleBlockPurge(const httplib::Request& req, httplib::Response& res);
void HandleBlockDuplicate(const httplib::Request& req, httplib::Response& res);
void HandleBlockRebase(const httplib::Request& req, httplib::Response& res);
void HandleBlockRebaseRecursive(const httplib::Request& req, httplib::Response& res);
void HandleBlockNested(const httplib::Request& req, httplib::Response& res);

// Deduplication
void HandleBlockCompare(const httplib::Request& req, httplib::Response& res);
void HandleBlockMerge(const httplib::Request& req, httplib::Response& res);

// Analysis
void HandleBlockLayerCensus(const httplib::Request& req, httplib::Response& res);

} // namespace Handlers
} // namespace Rook
