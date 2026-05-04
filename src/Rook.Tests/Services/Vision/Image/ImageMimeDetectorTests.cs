using Rook.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image
{
    public class ImageMimeDetectorTests
    {
        [Fact]
        public void Detects_png_signature()
        {
            var bytes = new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00 };

            Assert.Equal("image/png", ImageMimeDetector.Detect(bytes, "source.png"));
        }

        [Fact]
        public void Detects_jpeg_signature()
        {
            var bytes = new byte[] { 0xFF, 0xD8, 0xFF, 0xE0, 0x00 };

            Assert.Equal("image/jpeg", ImageMimeDetector.Detect(bytes, "source.jpg"));
        }

        [Fact]
        public void Detects_webp_signature()
        {
            var bytes = new byte[]
            {
                0x52, 0x49, 0x46, 0x46, 0x10, 0x00, 0x00, 0x00,
                0x57, 0x45, 0x42, 0x50
            };

            Assert.Equal("image/webp", ImageMimeDetector.Detect(bytes, "source.webp"));
        }

        [Theory]
        [InlineData("source.png")]
        [InlineData("source.jpg")]
        [InlineData("source.webp")]
        public void Returns_octet_stream_when_bytes_do_not_match_supported_image(string path)
        {
            Assert.Equal(
                "application/octet-stream",
                ImageMimeDetector.Detect(new byte[] { 1, 2, 3, 4 }, path));
        }

        [Theory]
        [InlineData(".png", "image/png")]
        [InlineData(".jpg", "image/jpeg")]
        [InlineData(".jpeg", "image/jpeg")]
        [InlineData(".webp", "image/webp")]
        [InlineData(".bmp", "image/bmp")]
        [InlineData(".gif", "image/gif")]
        [InlineData(".bin", "application/octet-stream")]
        public void FromExtension_matches_existing_picker_contract(string ext, string expected)
        {
            Assert.Equal(expected, ImageMimeDetector.FromExtension("x" + ext));
        }
    }
}
