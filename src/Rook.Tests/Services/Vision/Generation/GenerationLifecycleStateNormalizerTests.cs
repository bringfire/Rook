using System;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    public class GenerationLifecycleStateNormalizerTests
    {
        [Theory]
        [InlineData("pending", GenerationLifecycleState.Pending)]
        [InlineData("queued", GenerationLifecycleState.Pending)]
        [InlineData("in_queue", GenerationLifecycleState.Pending)]
        [InlineData("starting", GenerationLifecycleState.Pending)]
        [InlineData("submitted", GenerationLifecycleState.Pending)]
        [InlineData("running", GenerationLifecycleState.Running)]
        [InlineData("processing", GenerationLifecycleState.Running)]
        [InlineData("in_progress", GenerationLifecycleState.Running)]
        [InlineData("active", GenerationLifecycleState.Running)]
        [InlineData("completed", GenerationLifecycleState.Completed)]
        [InlineData("succeeded", GenerationLifecycleState.Completed)]
        [InlineData("success", GenerationLifecycleState.Completed)]
        [InlineData("done", GenerationLifecycleState.Completed)]
        [InlineData("finished", GenerationLifecycleState.Completed)]
        [InlineData("failed", GenerationLifecycleState.Failed)]
        [InlineData("error", GenerationLifecycleState.Failed)]
        [InlineData("errored", GenerationLifecycleState.Failed)]
        [InlineData("canceled", GenerationLifecycleState.Canceled)]
        [InlineData("cancelled", GenerationLifecycleState.Canceled)]
        public void Lowercase_values_normalize(string raw, GenerationLifecycleState expected)
        {
            Assert.Equal(expected, GenerationLifecycleStateNormalizer.Normalize(raw));
        }

        [Theory]
        // fal queue's UPPERCASE state names
        [InlineData("IN_QUEUE", GenerationLifecycleState.Pending)]
        [InlineData("IN_PROGRESS", GenerationLifecycleState.Running)]
        [InlineData("COMPLETED", GenerationLifecycleState.Completed)]
        // Mixed-case
        [InlineData("Running", GenerationLifecycleState.Running)]
        [InlineData("Succeeded", GenerationLifecycleState.Completed)]
        // Whitespace-padded
        [InlineData("  pending  ", GenerationLifecycleState.Pending)]
        public void Case_and_whitespace_are_normalized(string raw, GenerationLifecycleState expected)
        {
            Assert.Equal(expected, GenerationLifecycleStateNormalizer.Normalize(raw));
        }

        [Fact]
        public void TryNormalize_returns_false_for_unknown_state()
        {
            var ok = GenerationLifecycleStateNormalizer.TryNormalize("frobnicating", out _);
            Assert.False(ok);
        }

        [Fact]
        public void Normalize_throws_for_unknown_state()
        {
            var ex = Assert.Throws<ArgumentException>(
                () => GenerationLifecycleStateNormalizer.Normalize("frobnicating"));
            Assert.Contains("frobnicating", ex.Message);
        }

        [Fact]
        public void TryNormalize_returns_false_for_empty_input()
        {
            Assert.False(GenerationLifecycleStateNormalizer.TryNormalize("", out _));
            Assert.False(GenerationLifecycleStateNormalizer.TryNormalize("   ", out _));
        }
    }
}
