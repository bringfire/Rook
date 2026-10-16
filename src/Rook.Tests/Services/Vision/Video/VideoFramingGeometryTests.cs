using System;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class VideoFramingGeometryTests
    {
        [Theory]
        [InlineData(SourceFramingMode.Fit, 1380, 1080, 270, 0)]
        [InlineData(SourceFramingMode.Fill, 1920, 1502, 0, 211)]
        public void Geometry_MotivatingImageAndOddEdges(SourceFramingMode mode, int width, int height, int x, int y)
        {
            var result = VideoFramingGeometry.Create(new("image/png", 1166, 912), "1080p", "16:9", mode, "start_frame");
            Assert.Null(result.Error);
            var layout = result.Layout!;
            Assert.Equal((1920, 1080), (layout.CanvasWidth, layout.CanvasHeight));
            Assert.Equal((width, height), (layout.ScaledWidth, layout.ScaledHeight));
            Assert.Equal((x, y), (layout.OffsetX, layout.OffsetY));
            var odd = VideoFramingGeometry.Create(new("image/png", 119, 73), "720p", "16:9", SourceFramingMode.Fit, "start_frame").Layout!;
            Assert.Equal((1173, 720, 53, 0), (odd.ScaledWidth, odd.ScaledHeight, odd.OffsetX, odd.OffsetY));
        }

        [Fact]
        public void Geometry_ExtremeFillRejectedBeforeLaunchFitAdmitted()
        {
            var source = new VideoStillImageInfo("image/png", 16384, 720);
            var fill = VideoFramingGeometry.Create(source, "4k", "9:16", SourceFramingMode.Fill, "end_frame");
            Assert.Null(fill.Layout);
            Assert.Equal("source_preparation_failed", fill.Error!.ProviderErrorCode);
            Assert.Equal("render_limits_exceeded", fill.Error.ProviderDetail!["preparation_detail"].GetValue<string>());
            Assert.Equal("end_frame", fill.Error.Field);
            Assert.Equal("choose_fit", fill.Error.ProviderDetail["action"].GetValue<string>());
            var fit = VideoFramingGeometry.Create(source, "4k", "9:16", SourceFramingMode.Fit, "end_frame").Layout!;
            Assert.Equal((2160, 94), (fit.ScaledWidth, fit.ScaledHeight));
        }

        [Theory]
        [InlineData(1, 720, 480)]
        [InlineData(5, 720, 1080)]
        [InlineData(6, 720, 1080)]
        [InlineData(7, 720, 1080)]
        [InlineData(8, 720, 1080)]
        public void Geometry_OrientationPrecedesScaling(int orientation, int expectedWidth, int expectedHeight)
        {
            var result = VideoFramingGeometry.Create(new("image/jpeg", 3, 2, orientation), "720p", "9:16", SourceFramingMode.Fit, "start_frame");
            Assert.Null(result.Error);
            Assert.Equal((expectedWidth, expectedHeight), (result.Layout!.ScaledWidth, result.Layout.ScaledHeight));
        }

        [Theory]
        [InlineData(16385, 1)]
        [InlineData(8000, 4001)]
        [InlineData(int.MaxValue, int.MaxValue)]
        [InlineData(0, 1)]
        public void Geometry_OverflowAndRotationSurfaces(int width, int height)
        {
            var result = VideoFramingGeometry.Create(new("image/png", width, height, 6, 16, 4), "4k", "16:9", SourceFramingMode.Fill, "start_frame");
            Assert.Null(result.Layout);
            Assert.Equal("render_limits_exceeded", result.Error!.ProviderDetail!["preparation_detail"].GetValue<string>());
        }

        [Fact]
        public void Geometry_ThinSourceRemainsAtLeastOnePixel()
        {
            var result = VideoFramingGeometry.Create(new("image/png", 16384, 1), "720p", "9:16", SourceFramingMode.Fit, "start_frame");
            Assert.Equal(1, result.Layout!.ScaledHeight);
        }
    }
}
