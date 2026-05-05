using System;
using System.IO;

namespace Rook.Services.Vision.Image
{
    internal static class ImageMimeDetector
    {
        public static string Detect(byte[] bytes, string? path = null)
        {
            if (bytes is null || bytes.Length == 0)
                return "application/octet-stream";

            if (bytes.Length >= 8
                && bytes[0] == 0x89
                && bytes[1] == 0x50
                && bytes[2] == 0x4E
                && bytes[3] == 0x47
                && bytes[4] == 0x0D
                && bytes[5] == 0x0A
                && bytes[6] == 0x1A
                && bytes[7] == 0x0A)
            {
                return "image/png";
            }

            if (bytes.Length >= 3
                && bytes[0] == 0xFF
                && bytes[1] == 0xD8
                && bytes[2] == 0xFF)
            {
                return "image/jpeg";
            }

            if (bytes.Length >= 12
                && bytes[0] == 0x52
                && bytes[1] == 0x49
                && bytes[2] == 0x46
                && bytes[3] == 0x46
                && bytes[8] == 0x57
                && bytes[9] == 0x45
                && bytes[10] == 0x42
                && bytes[11] == 0x50)
            {
                return "image/webp";
            }

            return "application/octet-stream";
        }

        public static string FromExtension(string path)
        {
            var ext = Path.GetExtension(path ?? string.Empty).ToLowerInvariant();
            return ext switch
            {
                ".png" => "image/png",
                ".jpg" or ".jpeg" => "image/jpeg",
                ".webp" => "image/webp",
                ".gif" => "image/gif",
                ".bmp" => "image/bmp",
                _ => "application/octet-stream",
            };
        }

        public static bool IsPngJpegOrWebp(string mimeType) =>
            string.Equals(mimeType, "image/png", StringComparison.Ordinal)
            || string.Equals(mimeType, "image/jpeg", StringComparison.Ordinal)
            || string.Equals(mimeType, "image/webp", StringComparison.Ordinal);

        public static bool IsFlux2SupportedMime(string mimeType) =>
            IsPngJpegOrWebp(mimeType);
    }
}
