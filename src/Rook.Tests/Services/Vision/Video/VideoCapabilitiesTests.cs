using System.Collections.Generic;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class VideoCapabilitiesTests
    {
        // Helper — a default-shaped valid request the tests mutate.
        // Default PersonGeneration is AllowAll because the default mode
        // is T2V on a Veo 3.x model, which requires AllowAll. Tests that
        // exercise image-based modes set it to AllowAdult explicitly.
        private static VideoGenerationRequest DefaultRequest(
            string model = "veo-3.1-lite-generate-preview",
            VideoMode mode = VideoMode.T2V,
            int duration = 8,
            string resolution = "720p",
            string aspect = "16:9",
            string? prompt = "a flag flapping in the wind",
            int numberOfVideos = 1,
            VideoMediaRef? startFrame = null,
            VideoMediaRef? endFrame = null,
            IReadOnlyList<VideoMediaRef>? referenceFrames = null,
            PersonGenerationPolicy personGeneration = PersonGenerationPolicy.AllowAll) =>
            new(
                Model: model,
                Mode: mode,
                DurationSeconds: duration,
                Resolution: resolution,
                AspectRatio: aspect,
                Prompt: prompt,
                StartFrame: startFrame,
                EndFrame: endFrame,
                ReferenceFrames: referenceFrames,
                Seed: null,
                PersonGeneration: personGeneration,
                NumberOfVideos: numberOfVideos);

        // ─── Happy path ───────────────────────────────────────────────

        [Fact]
        public void Validate_accepts_default_t2v_lite()
        {
            var result = VideoCapabilities.Default.Validate(DefaultRequest());

            Assert.True(result.Success);
            Assert.Null(result.Field);
        }

        [Fact]
        public void Validate_accepts_t2v_full_3_1_at_4k_8s()
        {
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                model: "veo-3.1-generate-preview",
                resolution: "4k",
                duration: 8));

            Assert.True(result.Success);
        }

        // ─── Field-by-field rejections ────────────────────────────────

        [Fact]
        public void Validate_rejects_unknown_model()
        {
            var result = VideoCapabilities.Default.Validate(
                DefaultRequest(model: "veo-9000"));

            Assert.False(result.Success);
            Assert.Equal("Model", result.Field);
        }

        [Fact]
        public void Validate_rejects_unsupported_resolution()
        {
            var result = VideoCapabilities.Default.Validate(
                DefaultRequest(resolution: "8k"));

            Assert.False(result.Success);
            Assert.Equal("Resolution", result.Field);
        }

        [Fact]
        public void Validate_rejects_unsupported_aspect()
        {
            var result = VideoCapabilities.Default.Validate(
                DefaultRequest(aspect: "1:1"));

            Assert.False(result.Success);
            Assert.Equal("AspectRatio", result.Field);
        }

        [Fact]
        public void Validate_rejects_unsupported_duration()
        {
            var result = VideoCapabilities.Default.Validate(
                DefaultRequest(duration: 30));

            Assert.False(result.Success);
            Assert.Equal("DurationSeconds", result.Field);
        }

        [Fact]
        public void Validate_rejects_NumberOfVideos_greater_than_one()
        {
            var result = VideoCapabilities.Default.Validate(
                DefaultRequest(numberOfVideos: 2));

            Assert.False(result.Success);
            Assert.Equal("NumberOfVideos", result.Field);
        }

        [Fact]
        public void Validate_rejects_NumberOfVideos_zero()
        {
            var result = VideoCapabilities.Default.Validate(
                DefaultRequest(numberOfVideos: 0));

            Assert.False(result.Success);
            Assert.Equal("NumberOfVideos", result.Field);
        }

        [Fact]
        public void Validate_rejects_t2v_without_prompt()
        {
            var result = VideoCapabilities.Default.Validate(
                DefaultRequest(prompt: null));

            Assert.False(result.Success);
            Assert.Equal("Prompt", result.Field);
        }

        [Fact]
        public void Validate_rejects_i2v_without_start_frame()
        {
            // I2V on Veo 3.x requires PersonGeneration=AllowAdult per Veo docs.
            var result = VideoCapabilities.Default.Validate(
                DefaultRequest(
                    mode: VideoMode.I2V,
                    prompt: null,
                    personGeneration: PersonGenerationPolicy.AllowAdult));

            Assert.False(result.Success);
            Assert.Equal("StartFrame", result.Field);
        }

        [Fact]
        public void Validate_rejects_interp_without_end_frame()
        {
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
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
            // Lite model has SupportsReferenceImages=false.
            var refs = new[] { VideoMediaRef.ForPath(@"C:\fixtures\ref.png") };

            var result = VideoCapabilities.Default.Validate(
                DefaultRequest(referenceFrames: refs));

            Assert.False(result.Success);
            Assert.Equal("ReferenceFrames", result.Field);
        }

        [Fact]
        public void Validate_rejects_must8s_violation()
        {
            // 3.1 Lite at 1080p forces duration=8.
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                resolution: "1080p", duration: 4));

            Assert.False(result.Success);
            Assert.Equal("DurationSeconds", result.Field);
        }

        // ─── PersonGeneration validation (Veo API contract) ───────────

        [Fact]
        public void Validate_rejects_veo3_t2v_with_AllowAdult()
        {
            // Veo 3.x family T2V requires AllowAll per Google's docs.
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                personGeneration: PersonGenerationPolicy.AllowAdult));

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        [Fact]
        public void Validate_rejects_veo3_t2v_with_DontAllow()
        {
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                personGeneration: PersonGenerationPolicy.DontAllow));

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        [Fact]
        public void Validate_rejects_veo3_i2v_with_AllowAll()
        {
            // Veo 3.x family image-based modes require AllowAdult.
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                mode: VideoMode.I2V,
                prompt: null,
                startFrame: startFrame,
                personGeneration: PersonGenerationPolicy.AllowAll));

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        [Fact]
        public void Validate_accepts_veo3_i2v_with_AllowAdult()
        {
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                mode: VideoMode.I2V,
                prompt: null,
                startFrame: startFrame,
                personGeneration: PersonGenerationPolicy.AllowAdult));

            Assert.True(result.Success);
        }

        [Theory]
        [InlineData(PersonGenerationPolicy.AllowAll)]
        [InlineData(PersonGenerationPolicy.AllowAdult)]
        [InlineData(PersonGenerationPolicy.DontAllow)]
        public void Validate_accepts_veo2_t2v_with_any_policy(
            PersonGenerationPolicy policy)
        {
            // Veo 2 T2V allows any of the three values per Google's docs.
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                model: "veo-2.0-generate-001",
                resolution: "720p",
                duration: 8,
                personGeneration: policy));

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_veo2_i2v_with_AllowAll()
        {
            // Veo 2 image-based modes reject AllowAll (allow_adult or
            // dont_allow only per Google's docs).
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                model: "veo-2.0-generate-001",
                mode: VideoMode.I2V,
                resolution: "720p",
                duration: 8,
                prompt: null,
                startFrame: startFrame,
                personGeneration: PersonGenerationPolicy.AllowAll));

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        [Theory]
        [InlineData(PersonGenerationPolicy.AllowAdult)]
        [InlineData(PersonGenerationPolicy.DontAllow)]
        public void Validate_accepts_veo2_i2v_with_AllowAdult_or_DontAllow(
            PersonGenerationPolicy policy)
        {
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                model: "veo-2.0-generate-001",
                mode: VideoMode.I2V,
                resolution: "720p",
                duration: 8,
                prompt: null,
                startFrame: startFrame,
                personGeneration: policy));

            Assert.True(result.Success);
        }

        // ─── Undefined-enum guard (Codex round 4) ─────────────────────
        //
        // C# enums are coercible: (PersonGenerationPolicy)999 can reach
        // the catalog via casts, reflection, or a loose adapter. The
        // model/mode rules below only ever see defined values; an
        // explicit Enum.IsDefined guard rejects undefined values up
        // front. Tests pin the guard for both Veo 2 and Veo 3.x branches
        // — Veo 3.x happened to reject undefined values by accident
        // (its `!= AllowAll` checks treat anything else as wrong), but
        // the guard is the correct semantic boundary, so we pin it on
        // both branches to prevent silent regressions.

        [Fact]
        public void Validate_rejects_undefined_PersonGeneration_on_veo2_t2v()
        {
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                model: "veo-2.0-generate-001",
                resolution: "720p",
                duration: 8,
                personGeneration: (PersonGenerationPolicy)999));

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
            Assert.Contains("Unknown PersonGeneration", result.Message);
        }

        [Fact]
        public void Validate_rejects_undefined_PersonGeneration_on_veo2_i2v()
        {
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                model: "veo-2.0-generate-001",
                mode: VideoMode.I2V,
                resolution: "720p",
                duration: 8,
                prompt: null,
                startFrame: startFrame,
                personGeneration: (PersonGenerationPolicy)999));

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
            Assert.Contains("Unknown PersonGeneration", result.Message);
        }

        [Fact]
        public void Validate_rejects_undefined_PersonGeneration_on_veo3_t2v()
        {
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                personGeneration: (PersonGenerationPolicy)999));

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
            Assert.Contains("Unknown PersonGeneration", result.Message);
        }

        [Fact]
        public void Validate_rejects_undefined_PersonGeneration_on_veo3_i2v()
        {
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                mode: VideoMode.I2V,
                prompt: null,
                startFrame: startFrame,
                personGeneration: (PersonGenerationPolicy)999));

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
            Assert.Contains("Unknown PersonGeneration", result.Message);
        }

        [Fact]
        public void Validate_rejects_negative_undefined_PersonGeneration()
        {
            // Belt-and-suspenders: negative casts work the same way.
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                personGeneration: (PersonGenerationPolicy)(-1)));

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        // ─── Single-first-failure semantics ───────────────────────────

        [Fact]
        public void Validate_returns_first_failure_only()
        {
            // Both model and resolution are wrong; only the first failure
            // (Model) is reported. Pinning single-first-failure semantics.
            var result = VideoCapabilities.Default.Validate(DefaultRequest(
                model: "veo-9000",
                resolution: "8k"));

            Assert.False(result.Success);
            Assert.Equal("Model", result.Field);
        }

        // ─── TryGetModel ──────────────────────────────────────────────

        [Fact]
        public void TryGetModel_returns_known_model()
        {
            var ok = VideoCapabilities.Default.TryGetModel(
                "veo-3.1-lite-generate-preview", out var cap);

            Assert.True(ok);
            Assert.Equal("Veo 3.1 Lite", cap.Name);
        }

        [Fact]
        public void TryGetModel_returns_false_for_unknown()
        {
            var ok = VideoCapabilities.Default.TryGetModel(
                "veo-9000", out _);

            Assert.False(ok);
        }
    }
}
