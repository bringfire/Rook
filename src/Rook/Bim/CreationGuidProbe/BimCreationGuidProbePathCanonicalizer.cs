using System;
using System.IO;
using System.Security;

namespace Rook.Bim
{
    internal static class BimCreationGuidProbePathCanonicalizer
    {
        internal static bool TryCanonicalize(string input, out string canonical)
        {
            canonical = string.Empty;
            if (string.IsNullOrWhiteSpace(input) || input.IndexOf('\0') >= 0)
            {
                return false;
            }

            var normalizedInput = input.Replace('/', '\\');
            if (HasDeviceNamespacePrefix(normalizedInput) || !IsSupportedAbsoluteForm(normalizedInput))
            {
                return false;
            }

            string fullPath;
            try
            {
                fullPath = Path.GetFullPath(normalizedInput).Replace('/', '\\');
            }
            catch (Exception exception) when (exception is ArgumentException ||
                exception is NotSupportedException || exception is PathTooLongException ||
                exception is SecurityException)
            {
                return false;
            }

            if (HasDeviceNamespacePrefix(fullPath) || !IsSupportedAbsoluteForm(fullPath))
            {
                return false;
            }

            var root = Path.GetPathRoot(fullPath);
            if (string.IsNullOrEmpty(root) || !IsCompleteRoot(root))
            {
                return false;
            }

            if (IsDriveAbsolute(fullPath))
            {
                var driveRoot = char.ToUpperInvariant(fullPath[0]) + ":\\";
                canonical = string.Equals(fullPath, driveRoot, StringComparison.OrdinalIgnoreCase)
                    ? driveRoot : fullPath.TrimEnd('\\');
            }
            else
            {
                canonical = fullPath.TrimEnd('\\');
            }

            canonical = canonical.ToUpperInvariant();
            return canonical.Length > 0 && IsSupportedAbsoluteForm(canonical);
        }

        private static bool HasDeviceNamespacePrefix(string value)
        {
            return value.StartsWith(@"\\?\", StringComparison.OrdinalIgnoreCase) ||
                value.StartsWith(@"\\.\", StringComparison.OrdinalIgnoreCase) ||
                value.StartsWith(@"\??\", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsSupportedAbsoluteForm(string value)
        {
            return IsDriveAbsolute(value) || IsCompleteUnc(value);
        }

        private static bool IsDriveAbsolute(string value)
        {
            return value.Length >= 3 && char.IsLetter(value[0]) && value[1] == ':' && value[2] == '\\';
        }

        private static bool IsCompleteUnc(string value)
        {
            if (!value.StartsWith(@"\\", StringComparison.Ordinal))
            {
                return false;
            }

            var segments = value.Substring(2).Split('\\');
            return segments.Length >= 2 && !string.IsNullOrEmpty(segments[0]) &&
                !string.IsNullOrEmpty(segments[1]);
        }

        private static bool IsCompleteRoot(string root)
        {
            return IsDriveAbsolute(root) || IsCompleteUnc(root);
        }
    }
}
