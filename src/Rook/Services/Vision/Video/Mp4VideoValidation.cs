using System;
using System.Text;

namespace Rook.Services.Vision.Video
{
    // Validate the bounded ISO BMFF container before publication. Codec decoding
    // and quality are separate; a file-type header alone is not a video.
    internal static class Mp4VideoValidation
    {
        public static bool IsValid(byte[] bytes)
        {
            bool fileType = false, videoTrack = false, media = false;
            for (int offset = 0; offset < bytes.Length;)
            {
                if (!Box(bytes, offset, bytes.Length, out var type, out var payload, out var end)) return false;
                if (type == "ftyp") fileType |= end - payload >= 8;
                if (type == "mdat") media |= end > payload;
                if (type == "moov")
                {
                    for (int child = payload; child < end;)
                    {
                        if (!Box(bytes, child, end, out var childType, out var childPayload, out var childEnd)) return false;
                        if (childType == "trak") videoTrack |= VideoTrack(bytes, childPayload, childEnd);
                        child = childEnd;
                    }
                }
                offset = end;
            }
            return fileType && videoTrack && media;
        }
        private static bool VideoTrack(byte[] bytes, int start, int end)
        {
            if (!Find(bytes, start, end, "mdia", out var mdia, out var mdiaEnd)
                || !Find(bytes, mdia, mdiaEnd, "hdlr", out var handler, out var handlerEnd)
                || handlerEnd - handler < 12 || Encoding.ASCII.GetString(bytes, handler + 8, 4) != "vide"
                || !Find(bytes, mdia, mdiaEnd, "minf", out var minf, out var minfEnd)
                || !Find(bytes, minf, minfEnd, "stbl", out var stbl, out var stblEnd)
                || !Find(bytes, stbl, stblEnd, "stsd", out var stsd, out var stsdEnd)
                || stsdEnd - stsd < 8 || Read32(bytes, stsd + 4) == 0) return false;
            if (!Box(bytes, stsd + 8, stsdEnd, out var codec, out var sample, out var sampleEnd) || sampleEnd - sample < 78) return false;
            return codec is "avc1" or "avc3" or "hvc1" or "hev1" or "av01" or "vp09" or "mp4v" or "encv";
        }
        private static bool Find(byte[] bytes, int start, int end, string wanted, out int payload, out int boxEnd)
        {
            for (int offset = start; offset < end;)
            {
                if (!Box(bytes, offset, end, out var type, out payload, out boxEnd)) return false;
                if (type == wanted) return true;
                offset = boxEnd;
            }
            payload = boxEnd = 0; return false;
        }
        private static bool Box(byte[] bytes, int offset, int limit, out string type, out int payload, out int end)
        {
            type = ""; payload = end = 0;
            if (offset < 0 || limit > bytes.Length || limit - offset < 8) return false;
            ulong size = Read32(bytes, offset); int header = 8;
            if (size == 1)
            {
                if (limit - offset < 16) return false;
                size = ((ulong)Read32(bytes, offset + 8) << 32) | Read32(bytes, offset + 12); header = 16;
            }
            if (size == 0) size = (ulong)(limit - offset);
            if (size < (ulong)header || size > (ulong)(limit - offset)) return false;
            type = Encoding.ASCII.GetString(bytes, offset + 4, 4); payload = offset + header; end = offset + (int)size; return true;
        }
        private static uint Read32(byte[] bytes, int offset) => ((uint)bytes[offset] << 24) | ((uint)bytes[offset + 1] << 16) | ((uint)bytes[offset + 2] << 8) | bytes[offset + 3];
    }
}
