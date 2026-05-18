using System;

namespace Rook.Services.Vision.Image
{
    internal readonly struct ImageDimensions
    {
        public ImageDimensions(int width, int height)
        {
            if (width <= 0)
                throw new ArgumentOutOfRangeException(nameof(width));
            if (height <= 0)
                throw new ArgumentOutOfRangeException(nameof(height));

            Width = width;
            Height = height;
            PixelCount = (long)width * height;
        }

        public int Width { get; }

        public int Height { get; }

        public long PixelCount { get; }

        public static bool TryRead(byte[] bytes, string mimeType, out ImageDimensions dimensions)
        {
            dimensions = default;

            if (bytes is null || bytes.Length == 0 || string.IsNullOrWhiteSpace(mimeType))
                return false;

            try
            {
                if (string.Equals(mimeType, "image/png", StringComparison.Ordinal))
                    return TryReadPng(bytes, out dimensions);
                if (string.Equals(mimeType, "image/gif", StringComparison.Ordinal))
                    return TryReadGif(bytes, out dimensions);
                if (string.Equals(mimeType, "image/jpeg", StringComparison.Ordinal))
                    return TryReadJpeg(bytes, out dimensions);
                if (string.Equals(mimeType, "image/webp", StringComparison.Ordinal))
                    return TryReadWebp(bytes, out dimensions);
            }
            catch (ArgumentOutOfRangeException)
            {
                dimensions = default;
                return false;
            }
            catch (OverflowException)
            {
                dimensions = default;
                return false;
            }

            return false;
        }

        private static bool TryReadPng(byte[] bytes, out ImageDimensions dimensions)
        {
            dimensions = default;

            if (bytes.Length < 24
                || bytes[0] != 0x89
                || bytes[1] != 0x50
                || bytes[2] != 0x4E
                || bytes[3] != 0x47
                || bytes[4] != 0x0D
                || bytes[5] != 0x0A
                || bytes[6] != 0x1A
                || bytes[7] != 0x0A
                || ReadInt32BigEndian(bytes, 8) != 13
                || bytes[12] != 0x49
                || bytes[13] != 0x48
                || bytes[14] != 0x44
                || bytes[15] != 0x52)
            {
                return false;
            }

            return TryCreate(ReadInt32BigEndian(bytes, 16), ReadInt32BigEndian(bytes, 20), out dimensions);
        }

        private static bool TryReadGif(byte[] bytes, out ImageDimensions dimensions)
        {
            dimensions = default;

            if (bytes.Length < 10
                || bytes[0] != 0x47
                || bytes[1] != 0x49
                || bytes[2] != 0x46
                || bytes[3] != 0x38
                || (bytes[4] != 0x37 && bytes[4] != 0x39)
                || bytes[5] != 0x61)
            {
                return false;
            }

            return TryCreate(ReadUInt16LittleEndian(bytes, 6), ReadUInt16LittleEndian(bytes, 8), out dimensions);
        }

        private static bool TryReadJpeg(byte[] bytes, out ImageDimensions dimensions)
        {
            dimensions = default;

            if (bytes.Length < 4 || bytes[0] != 0xFF || bytes[1] != 0xD8)
                return false;

            var offset = 2;
            while (offset < bytes.Length)
            {
                if (bytes[offset] != 0xFF)
                    return false;

                while (offset < bytes.Length && bytes[offset] == 0xFF)
                    offset++;

                if (offset >= bytes.Length)
                    return false;

                var marker = bytes[offset++];
                if (marker == 0x00 || marker == 0xD8)
                    return false;
                if (marker == 0xD9 || marker == 0xDA)
                    return false;
                if (IsStandaloneJpegMarker(marker))
                    continue;

                if (offset + 2 > bytes.Length)
                    return false;

                var segmentLength = ReadUInt16BigEndian(bytes, offset);
                if (segmentLength < 2)
                    return false;

                var segmentStart = offset + 2;
                var segmentEnd = (long)offset + segmentLength;
                if (segmentEnd > bytes.Length)
                    return false;

                if (IsStartOfFrameMarker(marker))
                {
                    if (segmentLength < 7 || segmentStart + 5 > bytes.Length)
                        return false;

                    return TryCreate(
                        ReadUInt16BigEndian(bytes, segmentStart + 3),
                        ReadUInt16BigEndian(bytes, segmentStart + 1),
                        out dimensions);
                }

                offset = (int)segmentEnd;
            }

            return false;
        }

        private static bool TryReadWebp(byte[] bytes, out ImageDimensions dimensions)
        {
            dimensions = default;

            if (bytes.Length < 30
                || bytes[0] != 0x52
                || bytes[1] != 0x49
                || bytes[2] != 0x46
                || bytes[3] != 0x46
                || bytes[8] != 0x57
                || bytes[9] != 0x45
                || bytes[10] != 0x42
                || bytes[11] != 0x50)
            {
                return false;
            }

            var offset = 12;
            while (offset + 8 <= bytes.Length)
            {
                var chunkSize = ReadInt32LittleEndian(bytes, offset + 4);
                if (chunkSize < 0)
                    return false;

                var chunkDataStart = offset + 8;
                var chunkDataEnd = (long)chunkDataStart + chunkSize;
                if (chunkDataEnd > bytes.Length)
                    return false;

                if (bytes[offset] == 0x56
                    && bytes[offset + 1] == 0x50
                    && bytes[offset + 2] == 0x38
                    && bytes[offset + 3] == 0x58)
                {
                    if (chunkSize < 10)
                        return false;

                    var width = 1 + ReadUInt24LittleEndian(bytes, chunkDataStart + 4);
                    var height = 1 + ReadUInt24LittleEndian(bytes, chunkDataStart + 7);
                    return TryCreate(width, height, out dimensions);
                }

                offset = (int)chunkDataEnd + (chunkSize % 2);
            }

            return false;
        }

        private static bool TryCreate(int width, int height, out ImageDimensions dimensions)
        {
            dimensions = default;

            if (width <= 0 || height <= 0)
                return false;

            dimensions = new ImageDimensions(width, height);
            return true;
        }

        private static bool IsStandaloneJpegMarker(byte marker) =>
            marker == 0x01
            || (marker >= 0xD0 && marker <= 0xD7);

        private static bool IsStartOfFrameMarker(byte marker) =>
            marker == 0xC0
            || marker == 0xC1
            || marker == 0xC2
            || marker == 0xC3
            || marker == 0xC5
            || marker == 0xC6
            || marker == 0xC7
            || marker == 0xC9
            || marker == 0xCA
            || marker == 0xCB
            || marker == 0xCD
            || marker == 0xCE
            || marker == 0xCF;

        private static int ReadInt32BigEndian(byte[] bytes, int offset) =>
            (bytes[offset] << 24)
            | (bytes[offset + 1] << 16)
            | (bytes[offset + 2] << 8)
            | bytes[offset + 3];

        private static int ReadInt32LittleEndian(byte[] bytes, int offset) =>
            bytes[offset]
            | (bytes[offset + 1] << 8)
            | (bytes[offset + 2] << 16)
            | (bytes[offset + 3] << 24);

        private static int ReadUInt16BigEndian(byte[] bytes, int offset) =>
            (bytes[offset] << 8) | bytes[offset + 1];

        private static int ReadUInt16LittleEndian(byte[] bytes, int offset) =>
            bytes[offset] | (bytes[offset + 1] << 8);

        private static int ReadUInt24LittleEndian(byte[] bytes, int offset) =>
            bytes[offset] | (bytes[offset + 1] << 8) | (bytes[offset + 2] << 16);
    }
}
