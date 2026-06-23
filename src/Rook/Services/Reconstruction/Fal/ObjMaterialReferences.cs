using System;
using System.Collections.Generic;

namespace Rook.Services.Reconstruction.Fal;

/// <summary>
/// Pure, static MTL text parser that extracts the texture filenames referenced by
/// <c>map_*</c>, <c>bump</c>, and <c>norm</c> statements.  No I/O; no dependencies.
/// Used by Task-3 texture-integrity checking to detect missing delivered textures.
/// </summary>
public static class ObjMaterialReferences
{
    /// <summary>
    /// Returns the texture filenames referenced by <c>map_*</c> (any variant),
    /// <c>bump</c>, and <c>norm</c> statements in <paramref name="mtlText"/>.
    /// Options (e.g. <c>-bm 1.0</c>, <c>-s 1 1 1</c>) are stripped by taking the
    /// <em>last</em> whitespace-delimited token on each qualifying line.
    /// Results are in first-seen order, de-duplicated, and never empty strings.
    /// </summary>
    public static IReadOnlyList<string> ReferencedMapFileNames(string mtlText)
    {
        if (string.IsNullOrEmpty(mtlText))
            return Array.Empty<string>();

        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var result = new List<string>();

        foreach (var rawLine in mtlText.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line[0] == '#')
                continue;

            var tokens = line.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
            if (tokens.Length < 2)
                continue;

            var keyword = tokens[0];
            if (!IsMapKeyword(keyword))
                continue;

            // Last token is the filename; everything before it (after keyword) are options.
            var fileName = tokens[tokens.Length - 1].Trim();
            if (fileName.Length == 0)
                continue;

            if (seen.Add(fileName))
                result.Add(fileName);
        }

        return result;
    }

    /// <summary>
    /// Returns the filename for a single map keyword (e.g. <c>"map_Kd"</c>) from
    /// <paramref name="mtlText"/>, or <see langword="null"/> if the keyword is absent.
    /// Applies the same last-token / options-stripping rule as
    /// <see cref="ReferencedMapFileNames"/>.
    /// </summary>
    public static string? MapFileName(string mtlText, string keyword)
    {
        if (string.IsNullOrEmpty(mtlText) || string.IsNullOrEmpty(keyword))
            return null;

        foreach (var rawLine in mtlText.Split('\n'))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line[0] == '#')
                continue;

            var tokens = line.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
            if (tokens.Length < 2)
                continue;

            if (!string.Equals(tokens[0], keyword, StringComparison.OrdinalIgnoreCase))
                continue;

            var fileName = tokens[tokens.Length - 1].Trim();
            return fileName.Length == 0 ? null : fileName;
        }

        return null;
    }

    private static bool IsMapKeyword(string keyword)
    {
        // Case-insensitive: map_* covers all map variants; bump and norm are standalone keywords.
        if (keyword.StartsWith("map_", StringComparison.OrdinalIgnoreCase))
            return true;
        if (string.Equals(keyword, "bump", StringComparison.OrdinalIgnoreCase))
            return true;
        if (string.Equals(keyword, "norm", StringComparison.OrdinalIgnoreCase))
            return true;
        return false;
    }
}
