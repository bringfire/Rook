using System;
using System.IO;
using System.Security;
using System.Security.Cryptography;
using System.Text;

namespace Rook.Bim
{
    public static class BimDocumentKeyCodec
    {
        private const string FilePrefix = "file-document-v1:";
        private const string SavedPrefix = "saved-document-v1:";

        public static bool TryCanonicalizeWindowsPath(string? input, out string canonical)
        {
            canonical = string.Empty;
            if (input == null || string.IsNullOrWhiteSpace(input) || input.IndexOf('\0') >= 0)
            {
                return false;
            }

            try
            {
                var normalized = input.Replace('/', '\\');
                if (HasDevicePrefix(normalized) || !IsAbsoluteWindowsPath(normalized))
                {
                    return false;
                }

                var fullPath = Path.GetFullPath(normalized).Replace('/', '\\');
                if (HasDevicePrefix(fullPath) || !IsAbsoluteWindowsPath(fullPath))
                {
                    return false;
                }

                var root = Path.GetPathRoot(fullPath);
                if (string.IsNullOrEmpty(root) || !IsAbsoluteWindowsPath(root))
                {
                    return false;
                }

                if (IsUncPath(fullPath))
                {
                    canonical = fullPath.TrimEnd('\\');
                    if (!IsValidUnc(canonical))
                    {
                        canonical = string.Empty;
                        return false;
                    }
                }
                else
                {
                    var driveRoot = char.ToUpperInvariant(fullPath[0]) + @":\";
                    canonical = string.Equals(fullPath, driveRoot, StringComparison.OrdinalIgnoreCase)
                        ? driveRoot
                        : fullPath.TrimEnd('\\');
                }

                canonical = canonical.ToUpperInvariant();
                return true;
            }
            catch (ArgumentException)
            {
                canonical = string.Empty;
                return false;
            }
            catch (NotSupportedException)
            {
                canonical = string.Empty;
                return false;
            }
            catch (PathTooLongException)
            {
                canonical = string.Empty;
                return false;
            }
            catch (SecurityException)
            {
                canonical = string.Empty;
                return false;
            }
        }

        public static bool TryCreate(
            BimDocumentKeySource source,
            Guid creationGuid,
            string path,
            out string key)
        {
            key = string.Empty;
            if (creationGuid == Guid.Empty || !TryCanonicalizeWindowsPath(path, out var canonical))
            {
                return false;
            }

            var domain = DomainFor(source);
            var prefix = PrefixFor(source);
            if (domain == null || prefix == null)
            {
                return false;
            }

            try
            {
                var payload = domain + "\0" + creationGuid.ToString("D").ToLowerInvariant() + "\0" + canonical;
                var bytes = new UTF8Encoding(false, true).GetBytes(payload);
                using (var hash = SHA256.Create())
                {
                    key = prefix + ToLowerHex(hash.ComputeHash(bytes));
                    return true;
                }
            }
            catch (EncoderFallbackException)
            {
                key = string.Empty;
                return false;
            }
            catch (CryptographicException)
            {
                key = string.Empty;
                return false;
            }
        }

        public static bool IsValid(BimDocumentKeySource source, string? key)
        {
            var prefix = PrefixFor(source);
            if (prefix == null || key == null || !key.StartsWith(prefix, StringComparison.Ordinal))
            {
                return false;
            }

            if (key.Length != prefix.Length + 64)
            {
                return false;
            }

            for (var index = prefix.Length; index < key.Length; index++)
            {
                var value = key[index];
                if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
                {
                    return false;
                }
            }

            return true;
        }

        private static bool HasDevicePrefix(string path)
        {
            return path.StartsWith(@"\\?\", StringComparison.OrdinalIgnoreCase) ||
                path.StartsWith(@"\\.\", StringComparison.OrdinalIgnoreCase) ||
                path.StartsWith(@"\??\", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsAbsoluteWindowsPath(string path)
        {
            if (path.Length >= 3 && IsAsciiLetter(path[0]) && path[1] == ':' && path[2] == '\\')
            {
                return true;
            }

            return IsUncPath(path) && IsValidUnc(path);
        }

        private static bool IsUncPath(string path)
        {
            return path.Length >= 2 && path[0] == '\\' && path[1] == '\\';
        }

        private static bool IsValidUnc(string path)
        {
            if (!IsUncPath(path))
            {
                return false;
            }

            var remainder = path.Substring(2);
            var firstSeparator = remainder.IndexOf('\\');
            if (firstSeparator <= 0)
            {
                return false;
            }

            var shareStart = firstSeparator + 1;
            if (shareStart >= remainder.Length || remainder[shareStart] == '\\')
            {
                return false;
            }

            var shareEnd = remainder.IndexOf('\\', shareStart);
            return shareEnd < 0 || shareEnd > shareStart;
        }

        private static bool IsAsciiLetter(char value)
        {
            return (value >= 'A' && value <= 'Z') || (value >= 'a' && value <= 'z');
        }

        private static string? DomainFor(BimDocumentKeySource source)
        {
            switch (source)
            {
                case BimDocumentKeySource.RevitCreationGuidCentralPathV1:
                    return "rookbim:file-workshared:v1";
                case BimDocumentKeySource.RevitCreationGuidDocumentPathV1:
                    return "rookbim:saved-project:v1";
                default:
                    return null;
            }
        }

        private static string? PrefixFor(BimDocumentKeySource source)
        {
            switch (source)
            {
                case BimDocumentKeySource.RevitCreationGuidCentralPathV1:
                    return FilePrefix;
                case BimDocumentKeySource.RevitCreationGuidDocumentPathV1:
                    return SavedPrefix;
                default:
                    return null;
            }
        }

        private static string ToLowerHex(byte[] bytes)
        {
            var characters = new char[bytes.Length * 2];
            const string digits = "0123456789abcdef";
            for (var index = 0; index < bytes.Length; index++)
            {
                characters[index * 2] = digits[bytes[index] >> 4];
                characters[index * 2 + 1] = digits[bytes[index] & 0x0f];
            }

            return new string(characters);
        }
    }
}
