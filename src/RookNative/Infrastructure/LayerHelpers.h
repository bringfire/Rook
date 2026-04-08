// LayerHelpers.h
//
// Shared layer resolution utilities used by LayerOpsHandler, CreateHandler,
// and any handler that resolves layer references from API input.

#pragma once

#include <string>
#include <vector>

class CRhinoDoc;

namespace Rook {
namespace Infrastructure {

struct ResolvedLayerRef
{
    int index = -1;
    std::string fullPath;
};

/// Get the full layer path string (e.g. "Parent::Child") for a layer index.
std::string GetLayerFullPath(CRhinoDoc* pDoc, int layerIndex);

/// Resolve a layer reference by full path (exact) or leaf name (unambiguous).
/// Throws std::invalid_argument on empty, not-found, or ambiguous input.
ResolvedLayerRef ResolveLayerRef(CRhinoDoc* pDoc, const std::string& value, const char* fieldName);

/// Check if value contains the layer path separator "::".
bool ContainsPathSeparator(const std::string& value);

/// Validate that a layer name is a single segment (no "::").
/// Throws std::invalid_argument on empty or path-containing names.
void ValidateNewLayerName(const std::string& name);

/// Join parent path and name with "::" separator.
std::string JoinLayerPath(const std::string& parentPath, const std::string& name);

/// Check if a layer exists by full path (not deleted).
bool LayerExistsByFullPath(CRhinoDoc* pDoc, const std::string& fullPath);

} // namespace Infrastructure
} // namespace Rook
