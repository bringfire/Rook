using Rook.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ImageDimensionsTests
    {
        [Fact]
        public void Detect_recognizes_gif_bytes()
        {
            Assert.Equal("image/gif", ImageMimeDetector.Detect(GifBytes(640, 480)));
        }

        [Fact]
        public void IsFlux2SupportedMime_accepts_gif()
        {
            Assert.True(ImageMimeDetector.IsFlux2SupportedMime("image/gif"));
        }

        [Fact]
        public void TryRead_reads_gif_logical_screen_without_expanding_frames()
        {
            Assert.True(ImageDimensions.TryRead(GifBytes(320, 240), "image/gif", out var dimensions));
            Assert.Equal(320, dimensions.Width);
            Assert.Equal(240, dimensions.Height);
            Assert.Equal(76_800L, dimensions.PixelCount);
        }

        [Fact]
        public void TryRead_reads_png_ihdr_dimensions()
        {
            Assert.True(ImageDimensions.TryRead(PngBytes(1024, 768), "image/png", out var dimensions));
            Assert.Equal(1024, dimensions.Width);
            Assert.Equal(768, dimensions.Height);
        }

        [Fact]
        public void TryRead_reads_jpeg_sof_dimensions()
        {
            Assert.True(ImageDimensions.TryRead(JpegBytes(800, 600), "image/jpeg", out var dimensions));
            Assert.Equal(800, dimensions.Width);
            Assert.Equal(600, dimensions.Height);
        }

        [Fact]
        public void TryRead_reads_webp_vp8x_dimensions()
        {
            Assert.True(ImageDimensions.TryRead(WebpVp8xBytes(123, 456), "image/webp", out var dimensions));
            Assert.Equal(123, dimensions.Width);
            Assert.Equal(456, dimensions.Height);
        }

        [Fact]
        public void TryRead_reads_webp_vp8_lossy_dimensions()
        {
            Assert.True(ImageDimensions.TryRead(WebpVp8Bytes(321, 654), "image/webp", out var dimensions));
            Assert.Equal(321, dimensions.Width);
            Assert.Equal(654, dimensions.Height);
        }

        [Fact]
        public void TryRead_reads_webp_vp8l_lossless_dimensions()
        {
            Assert.True(ImageDimensions.TryRead(WebpVp8lBytes(222, 333), "image/webp", out var dimensions));
            Assert.Equal(222, dimensions.Width);
            Assert.Equal(333, dimensions.Height);
        }

        [Fact]
        public void TryRead_returns_false_for_truncated_image()
        {
            Assert.False(ImageDimensions.TryRead(new byte[] { 0x47, 0x49 }, "image/gif", out _));
        }

        [Fact]
        public void TryRead_returns_false_for_invalid_png_signature_with_ihdr_at_offset_12()
        {
            var bytes = PngBytes(1024, 768);
            bytes[0] = 0x00;

            Assert.False(ImageDimensions.TryRead(bytes, "image/png", out _));
        }

        [Fact]
        public void TryRead_returns_false_for_png_ihdr_length_not_13()
        {
            var bytes = PngBytes(1024, 768);
            WriteBigEndian(bytes, 8, 12);

            Assert.False(ImageDimensions.TryRead(bytes, "image/png", out _));
        }

        [Theory]
        [InlineData("image/gif")]
        [InlineData("image/png")]
        public void TryRead_returns_false_for_zero_dimensions(string mimeType)
        {
            var bytes = mimeType == "image/gif"
                ? GifBytes(0, 240)
                : PngBytes(1024, 0);

            Assert.False(ImageDimensions.TryRead(bytes, mimeType, out _));
        }

        [Fact]
        public void TryRead_returns_false_for_truncated_webp_vp8x()
        {
            var bytes = WebpVp8xBytes(123, 456);
            System.Array.Resize(ref bytes, 28);

            Assert.False(ImageDimensions.TryRead(bytes, "image/webp", out _));
        }

        [Fact]
        public void TryRead_returns_false_for_truncated_webp_vp8()
        {
            var bytes = WebpVp8Bytes(321, 654);
            System.Array.Resize(ref bytes, 29);

            Assert.False(ImageDimensions.TryRead(bytes, "image/webp", out _));
        }

        [Fact]
        public void TryRead_returns_false_for_webp_vp8_missing_start_code()
        {
            var bytes = WebpVp8Bytes(321, 654);
            bytes[23] = 0x00;

            Assert.False(ImageDimensions.TryRead(bytes, "image/webp", out _));
        }

        [Fact]
        public void TryRead_returns_false_for_truncated_webp_vp8l()
        {
            var bytes = WebpVp8lBytes(222, 333);
            System.Array.Resize(ref bytes, 24);

            Assert.False(ImageDimensions.TryRead(bytes, "image/webp", out _));
        }

        [Fact]
        public void TryRead_returns_false_for_webp_vp8l_missing_signature()
        {
            var bytes = WebpVp8lBytes(222, 333);
            bytes[20] = 0x00;

            Assert.False(ImageDimensions.TryRead(bytes, "image/webp", out _));
        }

        [Fact]
        public void TryRead_returns_false_for_jpeg_malformed_segment_boundary()
        {
            var bytes = new byte[]
            {
                0xFF, 0xD8,
                0xFF, 0xE0,
                0x00, 0x10,
                0x01, 0x02,
            };

            Assert.False(ImageDimensions.TryRead(bytes, "image/jpeg", out _));
        }

        [Fact]
        public void TryRead_returns_false_for_jpeg_non_marker_garbage_after_soi()
        {
            var bytes = new byte[]
            {
                0xFF, 0xD8,
                0x00,
                0xFF, 0xC0,
                0x00, 0x0B,
                0x08,
                0x02, 0x58,
                0x03, 0x20,
                0x03, 0x01, 0x11, 0x00,
                0x02, 0x11, 0x00,
                0x03, 0x11, 0x00,
            };

            Assert.False(ImageDimensions.TryRead(bytes, "image/jpeg", out _));
        }

        [Theory]
        [InlineData(0xD9)]
        [InlineData(0xDA)]
        public void TryRead_returns_false_for_jpeg_terminal_marker_before_sof(byte marker)
        {
            var bytes = new byte[]
            {
                0xFF, 0xD8,
                0xFF, marker,
                0x00, 0x02,
                0xFF, 0xC0,
                0x00, 0x0B,
                0x08,
                0x02, 0x58,
                0x03, 0x20,
                0x03, 0x01, 0x11, 0x00,
                0x02, 0x11, 0x00,
                0x03, 0x11, 0x00,
            };

            Assert.False(ImageDimensions.TryRead(bytes, "image/jpeg", out _));
        }

        private static byte[] GifBytes(int width, int height) =>
            new byte[]
            {
                0x47, 0x49, 0x46, 0x38, 0x39, 0x61,
                (byte)(width & 0xFF), (byte)((width >> 8) & 0xFF),
                (byte)(height & 0xFF), (byte)((height >> 8) & 0xFF),
                0x00, 0x00, 0x00,
            };

        private static byte[] PngBytes(int width, int height)
        {
            var bytes = new byte[33];
            bytes[0] = 0x89; bytes[1] = 0x50; bytes[2] = 0x4E; bytes[3] = 0x47;
            bytes[4] = 0x0D; bytes[5] = 0x0A; bytes[6] = 0x1A; bytes[7] = 0x0A;
            WriteBigEndian(bytes, 8, 13);
            bytes[12] = 0x49; bytes[13] = 0x48; bytes[14] = 0x44; bytes[15] = 0x52;
            WriteBigEndian(bytes, 16, width);
            WriteBigEndian(bytes, 20, height);
            return bytes;
        }

        private static byte[] JpegBytes(int width, int height) =>
            new byte[]
            {
                0xFF, 0xD8,
                0xFF, 0xE0,
                0x00, 0x04,
                0x00, 0x00,
                0xFF, 0xFF, 0xC0,
                0x00, 0x0B,
                0x08,
                (byte)((height >> 8) & 0xFF), (byte)(height & 0xFF),
                (byte)((width >> 8) & 0xFF), (byte)(width & 0xFF),
                0x03, 0x01, 0x11, 0x00,
                0x02, 0x11, 0x00,
                0x03, 0x11, 0x00,
            };

        private static byte[] WebpVp8xBytes(int width, int height)
        {
            var bytes = new byte[30];
            bytes[0] = 0x52; bytes[1] = 0x49; bytes[2] = 0x46; bytes[3] = 0x46;
            WriteLittleEndian(bytes, 4, 22);
            bytes[8] = 0x57; bytes[9] = 0x45; bytes[10] = 0x42; bytes[11] = 0x50;
            bytes[12] = 0x56; bytes[13] = 0x50; bytes[14] = 0x38; bytes[15] = 0x58;
            WriteLittleEndian(bytes, 16, 10);
            WriteUInt24LittleEndian(bytes, 24, width - 1);
            WriteUInt24LittleEndian(bytes, 27, height - 1);
            return bytes;
        }

        private static byte[] WebpVp8Bytes(int width, int height)
        {
            var bytes = new byte[30];
            bytes[0] = 0x52; bytes[1] = 0x49; bytes[2] = 0x46; bytes[3] = 0x46;
            WriteLittleEndian(bytes, 4, 22);
            bytes[8] = 0x57; bytes[9] = 0x45; bytes[10] = 0x42; bytes[11] = 0x50;
            bytes[12] = 0x56; bytes[13] = 0x50; bytes[14] = 0x38; bytes[15] = 0x20;
            WriteLittleEndian(bytes, 16, 10);
            bytes[20] = 0x00; bytes[21] = 0x00; bytes[22] = 0x00;
            bytes[23] = 0x9D; bytes[24] = 0x01; bytes[25] = 0x2A;
            WriteUInt16LittleEndian(bytes, 26, width);
            WriteUInt16LittleEndian(bytes, 28, height);
            return bytes;
        }

        private static byte[] WebpVp8lBytes(int width, int height)
        {
            var bytes = new byte[26];
            var widthMinusOne = width - 1;
            var heightMinusOne = height - 1;

            bytes[0] = 0x52; bytes[1] = 0x49; bytes[2] = 0x46; bytes[3] = 0x46;
            WriteLittleEndian(bytes, 4, 18);
            bytes[8] = 0x57; bytes[9] = 0x45; bytes[10] = 0x42; bytes[11] = 0x50;
            bytes[12] = 0x56; bytes[13] = 0x50; bytes[14] = 0x38; bytes[15] = 0x4C;
            WriteLittleEndian(bytes, 16, 5);
            bytes[20] = 0x2F;
            bytes[21] = (byte)(widthMinusOne & 0xFF);
            bytes[22] = (byte)(((widthMinusOne >> 8) & 0x3F) | ((heightMinusOne & 0x03) << 6));
            bytes[23] = (byte)((heightMinusOne >> 2) & 0xFF);
            bytes[24] = (byte)((heightMinusOne >> 10) & 0x0F);
            return bytes;
        }

        private static void WriteBigEndian(byte[] bytes, int offset, int value)
        {
            bytes[offset] = (byte)((value >> 24) & 0xFF);
            bytes[offset + 1] = (byte)((value >> 16) & 0xFF);
            bytes[offset + 2] = (byte)((value >> 8) & 0xFF);
            bytes[offset + 3] = (byte)(value & 0xFF);
        }

        private static void WriteLittleEndian(byte[] bytes, int offset, int value)
        {
            bytes[offset] = (byte)(value & 0xFF);
            bytes[offset + 1] = (byte)((value >> 8) & 0xFF);
            bytes[offset + 2] = (byte)((value >> 16) & 0xFF);
            bytes[offset + 3] = (byte)((value >> 24) & 0xFF);
        }

        private static void WriteUInt24LittleEndian(byte[] bytes, int offset, int value)
        {
            bytes[offset] = (byte)(value & 0xFF);
            bytes[offset + 1] = (byte)((value >> 8) & 0xFF);
            bytes[offset + 2] = (byte)((value >> 16) & 0xFF);
        }

        private static void WriteUInt16LittleEndian(byte[] bytes, int offset, int value)
        {
            bytes[offset] = (byte)(value & 0xFF);
            bytes[offset + 1] = (byte)((value >> 8) & 0xFF);
        }
    }
}
