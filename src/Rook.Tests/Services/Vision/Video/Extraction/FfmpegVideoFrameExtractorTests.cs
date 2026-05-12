using System;
using Rook.Services.Vision.Video.Extraction;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Extraction
{
    public sealed class FfmpegVideoFrameExtractorTests
    {
        [Fact]
        public void VideoFrameSelector_FirstIsFrameIndexZero()
        {
            var selector = VideoFrameSelector.First;

            Assert.Equal(VideoFrameSelectorKind.First, selector.Kind);
            Assert.Equal(0, selector.FrameIndexValue);
        }

        [Fact]
        public void VideoFrameSelector_FrameIndexUsesZeroBasedDecodedFrameIndex()
        {
            var selector = VideoFrameSelector.FrameIndex(42);

            Assert.Equal(VideoFrameSelectorKind.FrameIndex, selector.Kind);
            Assert.Equal(42, selector.FrameIndexValue);
        }

        [Fact]
        public void VideoFrameSelector_FrameIndexRejectsNegativeIndex()
        {
            var ex = Assert.Throws<ArgumentOutOfRangeException>(
                () => VideoFrameSelector.FrameIndex(-1));

            Assert.Equal("index", ex.ParamName);
        }

        [Fact]
        public void VideoFrameSelector_LastHasNoConcreteIndex()
        {
            var selector = VideoFrameSelector.Last;

            Assert.Equal(VideoFrameSelectorKind.Last, selector.Kind);
            Assert.Null(selector.FrameIndexValue);
        }
    }
}
