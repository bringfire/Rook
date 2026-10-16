using System;
using System.IO;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoStillImageInspectorTests
    {
        internal static string Fixture(string name)
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                var path = Path.Combine(directory.FullName, "third_party", "ffmpeg", "fixtures", "framing", name);
                if (File.Exists(path)) return path;
                directory = directory.Parent;
            }
            throw new FileNotFoundException("Framing fixture missing.", name);
        }
        [Theory]
        [InlineData("rgb-1166x912.png", "image/png", 1166, 912, 8)]
        [InlineData("rgb-1166x912.jpg", "image/jpeg", 1166, 912, 8)]
        [InlineData("rgb-1166x912-lossless.webp", "image/webp", 1166, 912, 8)]
        [InlineData("rgb-1166x912-lossy.webp", "image/webp", 1166, 912, 8)]
        [InlineData("alpha.webp", "image/webp", 128, 96, 8)]
        [InlineData("depth16.png", "image/png", 128, 96, 16)]
        [InlineData("palette.png", "image/png", 128, 96, 8)]
        public void Inspect_StaticAndNativeDepth(string file, string mime, int width, int height, int depth)
        {
            using var bytes = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(Fixture(file)), new VideoBufferBudget());
            var result = VideoStillImageInspector.Inspect(bytes, "start_frame");
            Assert.Null(result.Error);
            Assert.Equal((mime, width, height, depth), (result.Info!.MimeType, result.Info.Width, result.Info.Height, result.Info.BitDepth));
        }
        [Theory]
        [InlineData("animated.png")]
        [InlineData("declared-single.png")]
        [InlineData("animated.webp")]
        [InlineData("declared-single.webp")]
        public void Inspect_StaticAndDeclaredAnimation(string file)
        {
            using var bytes = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(Fixture(file)), new VideoBufferBudget());
            var result = VideoStillImageInspector.Inspect(bytes, "end_frame");
            Assert.Null(result.Info);
            Assert.Equal("source_animation_unsupported", result.Error!.ProviderErrorCode);
            Assert.Equal("end_frame", result.Error.Field);
        }
        [Theory]
        [InlineData("corrupt-crc.png")]
        [InlineData("corrupt-animation.png")]
        [InlineData("cyclic-exif.png")]
        [InlineData("chunk-overflow.webp")]
        public void Inspect_ChunkOverflowCyclicExifAndCorruptAnimation(string file)
        {
            using var bytes = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(Fixture(file)), new VideoBufferBudget());
            var result = VideoStillImageInspector.Inspect(bytes, "start_frame");
            Assert.Null(result.Info);
            Assert.Equal("invalid_source", result.Error!.ProviderDetail!["preparation_detail"].GetValue<string>());
        }
        [Theory]
        [InlineData("orientation-1.jpg", 1, 120, 80)]
        [InlineData("orientation-5.jpg", 5, 80, 120)]
        [InlineData("orientation-6.jpg", 6, 80, 120)]
        [InlineData("orientation-8.jpg", 8, 80, 120)]
        [InlineData("orientation-6.png", 6, 80, 120)]
        [InlineData("orientation-6.webp", 6, 80, 120)]
        public void Inspect_ExifFromEverySupportedContainer(string file, int orientation, int width, int height)
        {
            using var bytes = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(Fixture(file)), new VideoBufferBudget());
            var result = VideoStillImageInspector.Inspect(bytes, "start_frame");
            Assert.Null(result.Error);
            Assert.Equal((orientation, width, height), (result.Info!.Orientation, result.Info.OrientedWidth, result.Info.OrientedHeight));
        }
    }
}
