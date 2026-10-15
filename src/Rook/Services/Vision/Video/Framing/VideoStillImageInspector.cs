using System;
using System.Collections.Generic;

namespace Rook.Services.Vision.Video.Framing
{
    // Bounded container inspection only. Pixel decompression happens exclusively
    // in the memory-contained renderer after geometry admission.
    internal static class VideoStillImageInspector
    {
        private static readonly uint[] CrcTable = MakeCrcTable();
        public static VideoStillInspectionResult Inspect(VideoFrozenBuffer source, string field)
        {
            try { return source.Read(bytes => InspectBytes(bytes, field)); }
            catch (Exception ex) when (ex is InvalidContainerException or OverflowException or ArgumentOutOfRangeException or IndexOutOfRangeException)
            { return new(null, VideoSourcePreparationErrors.Create("source_preparation_failed", field, detail: "invalid_source")); }
        }
        private static VideoStillInspectionResult InspectBytes(ReadOnlySpan<byte> bytes, string field)
        {
            (VideoStillImageInfo Info, bool Animated) parsed;
            if (bytes.Length >= 8 && bytes[0] == 137 && Tag(bytes, 1, "PNG") &&
                bytes[4] == 13 && bytes[5] == 10 && bytes[6] == 26 && bytes[7] == 10) parsed = Png(bytes);
            else if (bytes.Length >= 12 && Tag(bytes, 0, "RIFF") && Tag(bytes, 8, "WEBP")) parsed = Webp(bytes);
            else if (bytes.Length >= 4 && bytes[0] == 255 && bytes[1] == 216) parsed = (Jpeg(bytes), false);
            else throw new InvalidContainerException();
            return parsed.Animated ? new(null, VideoSourcePreparationErrors.Create("source_animation_unsupported", field)) : new(parsed.Info, null);
        }
        private static (VideoStillImageInfo, bool) Png(ReadOnlySpan<byte> bytes)
        {
            int p = 8, width = 0, height = 0, depth = 0, color = -1, orientation = 1, frames = 0;
            uint declaredFrames = 0, sequence = 0;
            bool header = false, image = false, palette = false, end = false, transparency = false;
            bool animation = false, frameData = false, exif = false;
            while (p < bytes.Length)
            {
                Need(bytes, p, 12);
                uint length = Be32(bytes, p);
                Require((long)p + 12 + length <= bytes.Length);
                int n = checked((int)length), data = p + 8;
                for (int i = 0; i < 4; i++) Require(IsLetter(bytes[p + 4 + i]));
                Require(Crc(bytes.Slice(p + 4, n + 4)) == Be32(bytes, data + n));
                var value = bytes.Slice(data, n);
                if (Tag(bytes, p + 4, "IHDR"))
                {
                    Require(!header && p == 8 && n == 13);
                    width = checked((int)Be32(value, 0)); height = checked((int)Be32(value, 4));
                    depth = value[8]; color = value[9];
                    Require(width > 0 && height > 0 && value[10] == 0 && value[11] == 0 && value[12] <= 1);
                    Require(color switch {
                        0 => depth is 1 or 2 or 4 or 8 or 16, 2 or 4 or 6 => depth is 8 or 16,
                        3 => depth is 1 or 2 or 4 or 8, _ => false });
                    header = true;
                }
                else
                {
                    Require(header);
                    if (Tag(bytes, p + 4, "PLTE")) { Require(!palette && !image && n > 0 && n <= 768 && n % 3 == 0); palette = true; }
                    else if (Tag(bytes, p + 4, "IDAT")) { Require(color != 3 || palette); image = true; if (frames > 0) frameData = true; }
                    else if (Tag(bytes, p + 4, "tRNS")) { Require(!transparency && !image && color is 0 or 2 or 3); transparency = true; }
                    else if (Tag(bytes, p + 4, "eXIf")) { Require(!exif); orientation = Exif(value); exif = true; }
                    else if (Tag(bytes, p + 4, "acTL"))
                    { Require(!animation && !image && n == 8); declaredFrames = Be32(value, 0); Require(declaredFrames > 0); animation = true; }
                    else if (Tag(bytes, p + 4, "fcTL"))
                    {
                        Require(animation && n == 26 && (frames == 0 || frameData));
                        Require(Be32(value, 0) == sequence++); frames++; frameData = false;
                        long fw = Be32(value, 4), fh = Be32(value, 8), x = Be32(value, 12), y = Be32(value, 16);
                        Require(fw > 0 && fh > 0 && x + fw <= width && y + fh <= height && value[24] <= 2 && value[25] <= 1);
                    }
                    else if (Tag(bytes, p + 4, "fdAT"))
                    { Require(animation && frames > 0 && image && n > 4 && Be32(value, 0) == sequence++); frameData = true; }
                    else if (Tag(bytes, p + 4, "IEND"))
                    { Require(n == 0 && image && data + n + 4 == bytes.Length); end = true; }
                    else Require((bytes[p + 4] & 32) != 0); // unknown critical chunks are not this profile
                }
                p = checked(data + n + 4);
                if (end) break;
            }
            Require(header && image && end && (!animation || (frames == declaredFrames && frameData)));
            int planes = color switch { 0 => transparency ? 2 : 1, 2 => transparency ? 4 : 3, 4 => 2, _ => 4 };
            return (new("image/png", width, height, orientation, Math.Max(8, depth), planes), animation);
        }

        private static (VideoStillImageInfo, bool) Webp(ReadOnlySpan<byte> bytes)
        {
            Require((long)Le32(bytes, 4) + 8 == bytes.Length);
            int p = 12, width = 0, height = 0, orientation = 1, frames = 0;
            bool extended = false, animationFlag = false, animationHeader = false, still = false, exif = false;
            while (p < bytes.Length)
            {
                Need(bytes, p, 8);
                uint length = Le32(bytes, p + 4);
                Require((long)p + 8 + length + (length & 1) <= bytes.Length);
                int n = checked((int)length);
                var value = bytes.Slice(p + 8, n);
                if (Tag(bytes, p, "VP8X"))
                {
                    Require(!extended && p == 12 && n == 10 && (value[0] & 0xc1) == 0 &&
                        value[1] == 0 && value[2] == 0 && value[3] == 0);
                    extended = true; animationFlag = (value[0] & 2) != 0;
                    width = Le24(value, 4) + 1; height = Le24(value, 7) + 1;
                }
                else if (Tag(bytes, p, "ANIM"))
                { Require(extended && animationFlag && !animationHeader && !still && n == 6); animationHeader = true; }
                else if (Tag(bytes, p, "ANMF"))
                {
                    Require(animationHeader && n > 16);
                    int fw = Le24(value, 6) + 1, fh = Le24(value, 9) + 1;
                    Require(2L * Le24(value, 0) + fw <= width && 2L * Le24(value, 3) + fh <= height && (value[15] & 0xfc) == 0);
                    var encoded = WebpFrame(value.Slice(16));
                    Require(encoded.Width == fw && encoded.Height == fh); frames++;
                }
                else if (Tag(bytes, p, "VP8 ") || Tag(bytes, p, "VP8L"))
                {
                    Require(!still && !animationFlag);
                    var size = WebpBitstream(value, Tag(bytes, p, "VP8L"));
                    if (extended) Require(size.Width == width && size.Height == height);
                    else { width = size.Width; height = size.Height; }
                    still = true;
                }
                else if (Tag(bytes, p, "EXIF")) { Require(!exif); orientation = Exif(value); exif = true; }
                else if (Tag(bytes, p, "ALPH")) Require(extended && !animationFlag && !still && n > 0);
                p = checked(p + 8 + n + (n & 1));
            }
            Require(p == bytes.Length && width > 0 && height > 0 &&
                (animationFlag ? animationHeader && frames > 0 && !still : still && !animationHeader && frames == 0));
            // Four native components conservatively cover both lossy YUV and
            // lossless/alpha WebP decoder surfaces before RGBA normalization.
            return (new("image/webp", width, height, orientation, 8, 4), animationFlag);
        }
        private static (int Width, int Height) WebpFrame(ReadOnlySpan<byte> bytes)
        {
            int p = 0; (int Width, int Height)? size = null;
            while (p < bytes.Length)
            {
                Need(bytes, p, 8); uint length = Le32(bytes, p + 4);
                Require((long)p + 8 + length + (length & 1) <= bytes.Length); int n = checked((int)length);
                if (Tag(bytes, p, "VP8 ") || Tag(bytes, p, "VP8L"))
                { Require(size == null); size = WebpBitstream(bytes.Slice(p + 8, n), Tag(bytes, p, "VP8L")); }
                else Require(Tag(bytes, p, "ALPH") && size == null && n > 0);
                p = checked(p + 8 + n + (n & 1));
            }
            return size ?? throw new InvalidContainerException();
        }
        private static (int Width, int Height) WebpBitstream(ReadOnlySpan<byte> bytes, bool lossless)
        {
            if (lossless)
            { Need(bytes, 0, 5); Require(bytes[0] == 0x2f); uint bits = Le32(bytes, 1); Require((bits >> 29) == 0); return ((int)(bits & 0x3fff) + 1, (int)((bits >> 14) & 0x3fff) + 1); }
            Need(bytes, 0, 10); Require((bytes[0] & 1) == 0 && bytes[3] == 0x9d && bytes[4] == 1 && bytes[5] == 0x2a);
            int w = (bytes[6] | bytes[7] << 8) & 0x3fff, h = (bytes[8] | bytes[9] << 8) & 0x3fff;
            Require(w > 0 && h > 0); return (w, h);
        }

        private static VideoStillImageInfo Jpeg(ReadOnlySpan<byte> bytes)
        {
            int p = 2, width = 0, height = 0, depth = 0, planes = 0, orientation = 1;
            bool image = false, ended = false, exif = false;
            while (p < bytes.Length)
            {
                Require(bytes[p++] == 255);
                while (p < bytes.Length && bytes[p] == 255) p++;
                Need(bytes, p, 1); byte marker = bytes[p++];
                if (marker == 217) { ended = true; break; }
                if (marker is 0 or 216 || marker is >= 208 and <= 215) throw new InvalidContainerException();
                Need(bytes, p, 2); int length = Be16(bytes, p); Require(length >= 2); Need(bytes, p, length);
                var value = bytes.Slice(p + 2, length - 2);
                if (marker == 225 && value.Length >= 6 && Tag(value, 0, "Exif") && value[4] == 0 && value[5] == 0)
                { Require(!exif); orientation = Exif(value); exif = true; }
                if (marker is 192 or 193 or 194 or 195 or 197 or 198 or 199 or 201 or 202 or 203 or 205 or 206 or 207)
                {
                    Require(width == 0 && value.Length >= 6);
                    depth = value[0]; height = Be16(value, 1); width = Be16(value, 3); planes = value[5];
                    Require(width > 0 && height > 0 && planes is >= 1 and <= 4 && depth is >= 1 and <= 16 && value.Length == 6 + 3 * planes);
                }
                p += length;
                if (marker == 218)
                {
                    Require(width > 0); image = true;
                    while (p < bytes.Length)
                    {
                        if (bytes[p] != 255) { p++; continue; }
                        Need(bytes, p + 1, 1);
                        if (bytes[p + 1] == 0 || bytes[p + 1] is >= 208 and <= 215) { p += 2; continue; }
                        break;
                    }
                }
            }
            Require(image && ended && p == bytes.Length && width > 0);
            return new("image/jpeg", width, height, orientation, depth, planes);
        }

        private static int Exif(ReadOnlySpan<byte> bytes)
        {
            if (bytes.Length >= 6 && Tag(bytes, 0, "Exif") && bytes[4] == 0 && bytes[5] == 0) bytes = bytes.Slice(6);
            Need(bytes, 0, 8); bool little = bytes[0] == 73 && bytes[1] == 73;
            Require(little || bytes[0] == 77 && bytes[1] == 77);
            Require(U16(bytes, 2, little) == 42);
            int root = checked((int)U32(bytes, 4, little)), orientation = 1, entries = 0;
            var pending = new Stack<int>(); var visited = new HashSet<int>(); pending.Push(root);
            bool oriented = false;
            while (pending.Count > 0)
            {
                int offset = pending.Pop();
                Require(offset >= 8 && visited.Count < 64 && visited.Add(offset)); Need(bytes, offset, 2);
                int count = U16(bytes, offset, little); entries = checked(entries + count); Require(entries <= 16384);
                Need(bytes, offset + 2, checked(count * 12 + 4));
                for (int i = 0; i < count; i++)
                {
                    int at = offset + 2 + i * 12;
                    int tag = U16(bytes, at, little), type = U16(bytes, at + 2, little);
                    uint n = U32(bytes, at + 4, little);
                    int element = type switch { 1 or 2 or 6 or 7 => 1, 3 or 8 => 2, 4 or 9 or 11 or 13 => 4, 5 or 10 or 12 => 8, _ => 0 };
                    long size = checked((long)n * element);
                    if (element != 0 && size > 4) { uint pointer = U32(bytes, at + 8, little); Require(pointer >= 8 && pointer + size <= bytes.Length); }
                    if (tag == 274 && offset == root)
                    { Require(!oriented && type == 3 && n == 1); orientation = U16(bytes, at + 8, little); Require(orientation is >= 1 and <= 8); oriented = true; }
                    if (tag is 0x8769 or 0x8825 or 0xa005)
                    { Require(type == 4 && n == 1 && pending.Count < 64); uint pointer = U32(bytes, at + 8, little); if (pointer != 0) pending.Push(checked((int)pointer)); }
                }
                uint next = U32(bytes, offset + 2 + count * 12, little);
                if (next != 0) { Require(pending.Count < 64); pending.Push(checked((int)next)); }
            }
            return orientation;
        }
        private static int Be16(ReadOnlySpan<byte> bytes, int at) { Need(bytes, at, 2); return bytes[at] << 8 | bytes[at + 1]; }
        private static uint Be32(ReadOnlySpan<byte> bytes, int at) { Need(bytes, at, 4); return (uint)bytes[at] << 24 | (uint)bytes[at + 1] << 16 | (uint)bytes[at + 2] << 8 | bytes[at + 3]; }
        private static uint Le32(ReadOnlySpan<byte> bytes, int at) { Need(bytes, at, 4); return bytes[at] | (uint)bytes[at + 1] << 8 | (uint)bytes[at + 2] << 16 | (uint)bytes[at + 3] << 24; }
        private static int Le24(ReadOnlySpan<byte> bytes, int at) { Need(bytes, at, 3); return bytes[at] | bytes[at + 1] << 8 | bytes[at + 2] << 16; }
        private static int U16(ReadOnlySpan<byte> bytes, int at, bool little) { Need(bytes, at, 2); return little ? bytes[at] | bytes[at + 1] << 8 : Be16(bytes, at); }
        private static uint U32(ReadOnlySpan<byte> bytes, int at, bool little) => little ? Le32(bytes, at) : Be32(bytes, at);
        private static void Need(ReadOnlySpan<byte> bytes, int at, int count) => Require(at >= 0 && count >= 0 && (long)at + count <= bytes.Length);
        private static bool Tag(ReadOnlySpan<byte> bytes, int at, string tag)
        { if (at < 0 || (long)at + tag.Length > bytes.Length) return false; for (int i = 0; i < tag.Length; i++) if (bytes[at + i] != tag[i]) return false; return true; }
        private static bool IsLetter(byte b) => b is >= 65 and <= 90 or >= 97 and <= 122;
        private static void Require(bool condition) { if (!condition) throw new InvalidContainerException(); }
        private static uint Crc(ReadOnlySpan<byte> bytes)
        { uint crc = uint.MaxValue; foreach (byte b in bytes) crc = CrcTable[(crc ^ b) & 255] ^ (crc >> 8); return crc ^ uint.MaxValue; }
        private static uint[] MakeCrcTable()
        { var table = new uint[256]; for (uint i = 0; i < 256; i++) { uint value = i; for (int bit = 0; bit < 8; bit++) value = (value & 1) == 0 ? value >> 1 : 0xedb88320 ^ (value >> 1); table[i] = value; } return table; }
        private sealed class InvalidContainerException : Exception { }
    }
}
