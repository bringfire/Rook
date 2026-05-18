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
        public void TryRead_returns_false_for_truncated_image()
        {
            Assert.False(ImageDimensions.TryRead(new byte[] { 0x47, 0x49 }, "image/gif", out _));
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
            bytes[12] = 0x49; bytes[13] = 0x48; bytes[14] = 0x44; bytes[15] = 0x52;
            WriteBigEndian(bytes, 16, width);
            WriteBigEndian(bytes, 20, height);
            return bytes;
        }

        private static void WriteBigEndian(byte[] bytes, int offset, int value)
        {
            bytes[offset] = (byte)((value >> 24) & 0xFF);
            bytes[offset + 1] = (byte)((value >> 16) & 0xFF);
            bytes[offset + 2] = (byte)((value >> 8) & 0xFF);
            bytes[offset + 3] = (byte)(value & 0xFF);
        }
    }
}
