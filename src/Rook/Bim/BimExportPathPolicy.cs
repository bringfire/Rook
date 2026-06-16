using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Rook.Bim
{
    public static class BimExportPathPolicy
    {
        private static readonly char[] DisallowedNameChars =
            new[] { '/', '\\', ':', '*', '?', '"', '<', '>', '|' };

        // Windows reserved device names — illegal as file base names even with an extension.
        private static readonly HashSet<string> ReservedDeviceNames = new HashSet<string>(
            new[]
            {
                "CON", "PRN", "AUX", "NUL",
                "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
            },
            StringComparer.OrdinalIgnoreCase);

        // The supported output unit systems — kept in lockstep with the MCP tool schema enum and
        // RevitGeometryConverter.ScaleFromFeet. Validating here means an unknown unit fails fast at
        // the request boundary rather than silently degrading to a default downstream.
        private static readonly HashSet<string> SupportedUnits = new HashSet<string>(
            new[] { "meters", "millimeters", "centimeters", "feet", "inches" },
            StringComparer.OrdinalIgnoreCase);

        public static BimValidationResult ValidateRequestShape(BimExportOutput? output)
        {
            if (output == null)
            {
                return Fail("export output is required.");
            }

            if (!IsFullyQualifiedLocalDirectory(output.Directory))
            {
                return Fail("output.directory must be an absolute, fully-qualified local directory path.");
            }

            if (!IsSafeName(output.Name))
            {
                return Fail(
                    "output.name must be non-empty and contain only [A-Za-z0-9._-] (no separators, no '..').");
            }

            if (string.IsNullOrWhiteSpace(output.Units) || !SupportedUnits.Contains(output.Units))
            {
                return Fail(
                    "output.units must be one of: meters, millimeters, centimeters, feet, inches.");
            }

            return BimValidationResult.Ok;
        }

        public static bool IsSafeName(string? name)
        {
            if (string.IsNullOrWhiteSpace(name))
            {
                return false;
            }

            if (name!.IndexOf("..", StringComparison.Ordinal) >= 0)
            {
                return false;
            }

            if (name.IndexOfAny(DisallowedNameChars) >= 0)
            {
                return false;
            }

            if (!name.All(c => char.IsLetterOrDigit(c) || c == '.' || c == '_' || c == '-'))
            {
                return false;
            }

            // Reject Windows reserved device names (base name, ignoring any extension): CON, NUL, COM1, ...
            var dotIndex = name.IndexOf('.');
            var baseName = dotIndex >= 0 ? name.Substring(0, dotIndex) : name;
            return !ReservedDeviceNames.Contains(baseName);
        }

        public static BimExportArtifactPaths ResolveBundlePaths(string directory, string name)
        {
            return new BimExportArtifactPaths
            {
                Model3dm = Path.Combine(directory, name + ".3dm"),
                Sidecar = Path.Combine(directory, name + ".sidecar.json"),
                Validation = Path.Combine(directory, name + ".validation.json"),
            };
        }

        public static bool EscapesIntendedDirectory(string filePath, string directory)
        {
            var fullFile = Path.GetFullPath(filePath);
            var fullDir = Path.GetFullPath(directory);
            var normalizedDir = fullDir.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            return !fullFile.StartsWith(normalizedDir, StringComparison.OrdinalIgnoreCase);
        }

        // net48 has no Path.IsPathFullyQualified, so check manually:
        //  - must be drive-rooted "X:\..." or "X:/..." (NOT drive-relative "X:foo", which
        //    Path.IsPathRooted accepts), and
        //  - must NOT be a UNC path "\\server\share" (ambiguous local target).
        private static bool IsFullyQualifiedLocalDirectory(string? directory)
        {
            if (string.IsNullOrWhiteSpace(directory))
            {
                return false;
            }

            var dir = directory!;
            if (dir.StartsWith(@"\\", StringComparison.Ordinal) || dir.StartsWith("//", StringComparison.Ordinal))
            {
                return false; // UNC
            }

            return dir.Length >= 3 &&
                ((dir[0] >= 'A' && dir[0] <= 'Z') || (dir[0] >= 'a' && dir[0] <= 'z')) &&
                dir[1] == ':' &&
                (dir[2] == '\\' || dir[2] == '/');
        }

        private static BimValidationResult Fail(string message)
        {
            return new BimValidationResult
            {
                Success = false,
                ErrorCode = BimErrorCode.OutputPathInvalid,
                Message = message
            };
        }
    }
}
