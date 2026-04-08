// PathValidation.h
//
// Lexical validation of user-supplied file paths. All checks are textual —
// no OS calls, no canonicalization. The path is rejected or accepted based
// on its content alone.

#pragma once
#include <string>
#include <filesystem>

namespace Rook {

inline bool IsPathSeparator(char c) { return c == '\\' || c == '/'; }

/// Validate a user-supplied file path.
/// Returns empty string on success, or an error message on rejection.
inline std::string ValidateFilePath(const std::string& path)
{
    if (path.empty())
        return "File path is empty";

    // Reject control characters and quotes.
    // Control chars include \n and \r which are RunScript command separators.
    // Quotes break RunScript string interpolation used by import/export.
    for (unsigned char c : path)
    {
        if (c < 0x20)
            return "File path contains control characters";
        if (c == '"')
            return "File path contains quote characters";
    }

    // Reject UNC paths (\\server\share), device namespace paths (\\?\, \\.\),
    // and forward-slash equivalents (//server/share).
    if (path.size() >= 2 && IsPathSeparator(path[0]) && IsPathSeparator(path[1]))
        return "UNC and device namespace paths are not permitted";

    // Reject path traversal: any ".." component detected via lexical
    // std::filesystem::path iteration. This catches \..\, /../, C:..\,
    // trailing \.., and leading ..\ without needing OS resolution.
    const std::filesystem::path lexical(path);
    for (const auto& part : lexical)
    {
        if (part == "..")
            return "Path traversal (..) is not permitted";
    }

    return "";  // valid
}

} // namespace Rook
