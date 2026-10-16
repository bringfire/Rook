using System;
using System.IO;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public sealed class FfmpegVideoSourceValidatorTests
    {
        [Theory]
        [InlineData("unenforced", "enforcement_unavailable")]
        [InlineData("memory", "render_limits_exceeded")]
        [InlineData("diagnostic", "invalid_source")]
        [InlineData("oversized_output", "invalid_output")]
        public async Task DecoderFailuresAreClosedAndReleaseScratchAndTemporaryFiles(string failure, string detail)
        {
            var runner = new Runner { Failure = failure };
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            using var snapshot = Snapshot();
            var error = await new FfmpegVideoSourceValidator(runner, () => VideoSourceRendererTests.Binary).ValidateAsync(snapshot.Slots[0], phase, default);
            Assert.Equal(detail, error!.ProviderDetail!["preparation_detail"].GetValue<string>());
            Assert.Equal("start_frame", error.Field); Assert.Equal(0, phase.Buffers.ReservedBytes);
            Assert.False(Directory.Exists(runner.Root));
            Assert.Contains("-xerror", runner.Request!.Arguments);
            Assert.Contains("crccheck+bitstream+buffer+explode", runner.Request.Arguments);
        }
        [Fact]
        public async Task CancellationDrainsOwnedWorkBeforeReleasingTemporarySource()
        {
            var runner = new Runner { Failure = "block" };
            using var phase = await new VideoPreparationResources().AcquireAsync(default);
            using var snapshot = Snapshot(); using var stop = new CancellationTokenSource();
            var validation = new FfmpegVideoSourceValidator(runner, () => VideoSourceRendererTests.Binary).ValidateAsync(snapshot.Slots[0], phase, stop.Token);
            await runner.Entered.Task; Assert.True(Directory.Exists(runner.Root)); stop.Cancel();
            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => validation);
            Assert.False(Directory.Exists(runner.Root)); Assert.Equal(0, phase.Buffers.ReservedBytes);
        }
        [Fact]
        public async Task InvalidRendererProfileNeverLaunchesOrLeavesReservations()
        {
            var runner = new Runner(); using var phase = await new VideoPreparationResources().AcquireAsync(default); using var snapshot = Snapshot();
            var error = await new FfmpegVideoSourceValidator(runner, () => null).ValidateAsync(snapshot.Slots[0], phase, default);
            Assert.Equal("renderer_unavailable", error!.ProviderDetail!["preparation_detail"].GetValue<string>());
            Assert.Null(runner.Request); Assert.Equal(0, phase.Buffers.ReservedBytes);
        }
        private static VideoPreparedMediaSnapshot Snapshot()
        {
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.I2V, startFrame: source);
            return VideoPreparedMediaSnapshot.Capture(request, new Dictionary<MediaRef, ResolvedMedia> {
                [source] = new(File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("matching.png")), "image/png") });
        }
        private sealed class Runner : IFramingProcessRunner
        {
            internal string Failure = "";
            internal string? Root;
            internal FramingProcessRequest? Request;
            internal readonly TaskCompletionSource<bool> Entered = new(TaskCreationOptions.RunContinuationsAsynchronously);
            public async Task<FramingProcessResult> RunAsync(FramingProcessRequest request, CancellationToken ct)
            {
                Request = request; Root = request.WorkingDirectory; Entered.TrySetResult(true);
                if (Failure == "block") await Task.Delay(Timeout.Infinite, ct);
                if (Failure == "oversized_output") using (var file = File.OpenWrite(request.OutputPath)) file.SetLength(4097);
                return new(Failure != "memory", Failure == "memory" ? "render_limits_exceeded" : null, 1, Failure != "unenforced", Failure == "diagnostic" ? "synthetic decoder error" : "", 0, 1);
            }
        }
    }
}
