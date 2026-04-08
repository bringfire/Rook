// LayerHelpers.cpp
//
// Shared layer resolution utilities.

#include "stdafx.h"
#include "Infrastructure/LayerHelpers.h"
#include "Infrastructure/JsonHelpers.h"

#include <cctype>
#include <stdexcept>

namespace Rook {
namespace Infrastructure {

static constexpr const char* kLayerPathSeparator = "::";

static std::string SummarizeLayerMatches(CRhinoDoc* pDoc, const std::vector<int>& matches)
{
    std::string summary;
    constexpr size_t kPreviewCount = 3;

    for (size_t i = 0; i < matches.size() && i < kPreviewCount; ++i)
    {
        if (!summary.empty())
            summary += ", ";
        summary += "'" + GetLayerFullPath(pDoc, matches[i]) + "'";
    }

    if (matches.size() > kPreviewCount)
        summary += ", ...";

    return summary;
}

std::string GetLayerFullPath(CRhinoDoc* pDoc, int layerIndex)
{
    ON_wString fullPath;
    pDoc->m_layer_table.GetLayerPathName(layerIndex, fullPath);
    return WideToUtf8(fullPath);
}

std::string JoinLayerPath(const std::string& parentPath, const std::string& name)
{
    if (parentPath.empty())
        return name;
    return parentPath + kLayerPathSeparator + name;
}

bool ContainsPathSeparator(const std::string& value)
{
    return value.find(kLayerPathSeparator) != std::string::npos;
}

bool LayerExistsByFullPath(CRhinoDoc* pDoc, const std::string& fullPath)
{
    ON_wString wPath = Utf8ToWide(fullPath);
    const int idx = pDoc->m_layer_table.FindLayerFromFullPathName(
        static_cast<const wchar_t*>(wPath), -1);
    return idx >= 0 && !pDoc->m_layer_table[idx].IsDeleted();
}

void ValidateNewLayerName(const std::string& name)
{
    if (name.empty())
        throw std::invalid_argument("Layer name cannot be empty");

    if (ContainsPathSeparator(name))
    {
        throw std::invalid_argument(
            "Layer name cannot contain '::'. Use the 'parent' field or "
            "the batch layer API to define hierarchy.");
    }
}

ResolvedLayerRef ResolveLayerRef(CRhinoDoc* pDoc, const std::string& value, const char* fieldName)
{
    if (value.empty())
        throw std::invalid_argument(std::string("'") + fieldName + "' cannot be empty");

    ON_wString wValue = Utf8ToWide(value);
    const int exactIdx = pDoc->m_layer_table.FindLayerFromFullPathName(
        static_cast<const wchar_t*>(wValue), -1);
    if (exactIdx >= 0 && !pDoc->m_layer_table[exactIdx].IsDeleted())
        return { exactIdx, GetLayerFullPath(pDoc, exactIdx) };

    std::vector<int> leafMatches;
    for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
    {
        const CRhinoLayer& layer = pDoc->m_layer_table[i];
        if (layer.IsDeleted())
            continue;
        if (layer.Name().CompareNoCase(wValue) == 0)
            leafMatches.push_back(i);
    }

    if (leafMatches.empty())
        throw std::invalid_argument(std::string("Layer '") + value + "' not found");

    if (leafMatches.size() > 1)
    {
        throw std::invalid_argument(
            std::string("'") + fieldName + "' value '" + value +
            "' is ambiguous; use the full layer path. Matches: " +
            SummarizeLayerMatches(pDoc, leafMatches));
    }

    return { leafMatches.front(), GetLayerFullPath(pDoc, leafMatches.front()) };
}

} // namespace Infrastructure
} // namespace Rook
