using System.Text.Json;
using Rook.Handlers;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fixtures
{
    /// <summary>
    /// Captures the V1c <c>estimate_video_job</c> wire response by
    /// driving <see cref="VideoOpHandler.DispatchOffUi"/> end-to-end.
    /// The capture goes through the same code path the native HTTP
    /// route exercises in production — production projection
    /// (<c>VideoOpHandler.Estimate</c>) is the source of the golden
    /// bytes, so any drift there breaks the assertion.
    ///
    /// <para>Drives a real <see cref="DefaultVideoProviderRegistry"/>
    /// + real <see cref="VideoCostEstimator"/> + a fake
    /// <see cref="IVideoJobManager"/> (estimate does not touch the
    /// manager, but the handler's constructor requires one).</para>
    /// </summary>
    public class VeoCostEstimateCaptureTests
    {
        [Fact]
        public void Golden_10_cost_estimate_veo_3_1_1080p_8s()
        {
            // Veo 3.1 full @ 1080p × 8s × 1 video — exercises
            // PerSecondPricingModel via VideoCostEstimator. Per
            // VeoCapabilities, 1080p costs $0.40/s on Veo 3.1, so the
            // captured Total is the audit-snapshot of that rate.
            var registry = TestVideoFixtures.RegistryWithVeo();
            var estimator = new VideoCostEstimator();
            var manager = new FakeVideoJobManager();  // estimate path doesn't reach the manager

            var handler = new VideoOpHandler(manager, registry, estimator);

            var body = JsonSerializer.Serialize(new
            {
                op = VideoOpHandler.OpEstimate,
                model = "veo-3.1-generate-preview",
                mode = "t2v",
                duration_seconds = 8,
                resolution = "1080p",
                aspect_ratio = "16:9",
                prompt = "a cinematic shot of a coastline at dusk",
                options = new { person_generation = "allow_all" },
                number_of_videos = 1,
            });

            var response = handler.DispatchOffUi(body);
            Assert.True(response.Success,
                "estimate_video_job should succeed in this fixture; got: "
                + ApiResponseSerializer.ToJson(response));

            var json = ApiResponseSerializer.ToJson(response);
            VeoBehaviorParityFixture.AssertOrCapture(
                "10_cost_estimate_veo_3_1_1080p_8s.json", json);
        }
    }
}
