using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// Provider-neutral request-shape validation. Lifted from V1b's
    /// <c>VideoCapabilitiesTests</c> minus the PersonGeneration tests
    /// (which moved to <see cref="VeoOptionsCodecTests"/>) and minus the
    /// model-existence tests (which the registry now owns).
    /// </summary>
    public class CapabilityValidatorTests
    {
        private static (VideoCapability cap, object _) Lite =>
            VeoCapabilities.Models["veo-3.1-lite-generate-preview"];
        private static (VideoCapability cap, object _) Full31 =>
            VeoCapabilities.Models["veo-3.1-generate-preview"];

        // ─── Happy path ───────────────────────────────────────────────

        [Fact]
        public void Validate_accepts_default_t2v_lite()
        {
            var result = CapabilityValidator.Validate(
                Lite.cap, TestVideoFixtures.DefaultT2vRequest());

            Assert.True(result.Success);
            Assert.Null(result.Field);
        }

        [Fact]
        public void Validate_accepts_t2v_full_3_1_at_4k_8s()
        {
            var result = CapabilityValidator.Validate(
                Full31.cap,
                TestVideoFixtures.DefaultT2vRequest(
                    model: "veo-3.1-generate-preview",
                    resolution: "4k",
                    duration: 8));

            Assert.True(result.Success);
        }

        // ─── Field-by-field rejections ────────────────────────────────

        [Fact]
        public void Validate_rejects_unsupported_resolution()
        {
            var result = CapabilityValidator.Validate(
                Lite.cap,
                TestVideoFixtures.DefaultT2vRequest(resolution: "8k"));

            Assert.False(result.Success);
            Assert.Equal("Resolution", result.Field);
        }

        [Fact]
        public void Validate_rejects_unsupported_aspect()
        {
            var result = CapabilityValidator.Validate(
                Lite.cap,
                TestVideoFixtures.DefaultT2vRequest(aspect: "1:1"));

            Assert.False(result.Success);
            Assert.Equal("AspectRatio", result.Field);
        }

        [Fact]
        public void Validate_rejects_unsupported_duration()
        {
            var result = CapabilityValidator.Validate(
                Lite.cap,
                TestVideoFixtures.DefaultT2vRequest(duration: 30));

            Assert.False(result.Success);
            Assert.Equal("DurationSeconds", result.Field);
        }

        [Fact]
        public void Validate_rejects_NumberOfVideos_greater_than_one()
        {
            var result = CapabilityValidator.Validate(
                Lite.cap,
                TestVideoFixtures.DefaultT2vRequest(numberOfVideos: 2));

            Assert.False(result.Success);
            Assert.Equal("NumberOfVideos", result.Field);
        }

        [Fact]
        public void Validate_rejects_NumberOfVideos_zero()
        {
            var result = CapabilityValidator.Validate(
                Lite.cap,
                TestVideoFixtures.DefaultT2vRequest(numberOfVideos: 0));

            Assert.False(result.Success);
            Assert.Equal("NumberOfVideos", result.Field);
        }

        [Fact]
        public void Validate_rejects_t2v_without_prompt()
        {
            var result = CapabilityValidator.Validate(
                Lite.cap,
                TestVideoFixtures.DefaultT2vRequest(prompt: null));

            Assert.False(result.Success);
            Assert.Equal("Prompt", result.Field);
        }

        [Fact]
        public void Validate_rejects_i2v_without_start_frame()
        {
            var result = CapabilityValidator.Validate(
                Full31.cap,
                TestVideoFixtures.DefaultT2vRequest(
                    model: "veo-3.1-generate-preview",
                    mode: VideoMode.I2V,
                    prompt: null,
                    personGeneration: PersonGenerationPolicy.AllowAdult));

            Assert.False(result.Success);
            Assert.Equal("StartFrame", result.Field);
        }

        [Fact]
        public void Validate_rejects_interp_without_end_frame()
        {
            var startFrame = MediaRef.ForPath(
                @"C:\fixtures\start.png", VideoMediaRoles.Image);
            var result = CapabilityValidator.Validate(
                Full31.cap,
                TestVideoFixtures.DefaultT2vRequest(
                    model: "veo-3.1-generate-preview",
                    mode: VideoMode.Interp,
                    prompt: null,
                    startFrame: startFrame,
                    endFrame: null,
                    personGeneration: PersonGenerationPolicy.AllowAdult));

            Assert.False(result.Success);
            Assert.Equal("EndFrame", result.Field);
        }

        [Fact]
        public void Validate_rejects_reference_frames_on_lite_model()
        {
            // Lite cap: SupportsReferenceImages=false.
            var refs = new[]
            {
                MediaRef.ForPath(@"C:\fixtures\ref.png", VideoMediaRoles.Image),
            };

            var result = CapabilityValidator.Validate(
                Lite.cap,
                TestVideoFixtures.DefaultT2vRequest(referenceFrames: refs));

            Assert.False(result.Success);
            Assert.Equal("ReferenceFrames", result.Field);
        }

        [Fact]
        public void Validate_rejects_must8s_violation()
        {
            // 3.1 Lite at 1080p forces duration=8.
            var result = CapabilityValidator.Validate(
                Lite.cap,
                TestVideoFixtures.DefaultT2vRequest(resolution: "1080p", duration: 4));

            Assert.False(result.Success);
            Assert.Equal("DurationSeconds", result.Field);
        }

        [Fact]
        public void Validate_rejects_unsupported_mode_on_cap()
        {
            // Construct a one-mode cap for symmetry; lite ships I2V too,
            // so we have to fabricate a cap to test mode rejection.
            var t2vOnly = new VideoCapability(
                Id: "x", Name: "X", Status: "preview",
                Resolutions: new[] { "720p" },
                Durations: new[] { 8 },
                AspectRatios: new[] { "16:9" },
                Modes: new[] { VideoMode.T2V },
                SupportsReferenceImages: false,
                MaxReferenceImages: 0,
                Must8sWith: System.Array.Empty<string>());

            var result = CapabilityValidator.Validate(
                t2vOnly,
                TestVideoFixtures.DefaultT2vRequest(
                    model: "x", mode: VideoMode.I2V, prompt: null,
                    startFrame: MediaRef.ForPath(@"C:\x.png", VideoMediaRoles.Image),
                    personGeneration: PersonGenerationPolicy.AllowAdult));

            Assert.False(result.Success);
            Assert.Equal("Mode", result.Field);
        }

        // ─── Null guards ──────────────────────────────────────────────

        [Fact]
        public void Validate_rejects_null_request()
        {
            var result = CapabilityValidator.Validate(Lite.cap, request: null!);

            Assert.False(result.Success);
            Assert.Equal("Request", result.Field);
        }

        [Fact]
        public void Validate_rejects_null_cap()
        {
            var result = CapabilityValidator.Validate(
                cap: null!, TestVideoFixtures.DefaultT2vRequest());

            Assert.False(result.Success);
            Assert.Equal("Cap", result.Field);
        }
    }
}
