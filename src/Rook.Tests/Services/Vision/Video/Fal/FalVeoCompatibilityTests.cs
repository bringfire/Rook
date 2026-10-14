using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVeoCompatibilityTests
    {
        internal static FalVeoBindingCatalog ActiveCatalog() => new(new FalVeoBindingCatalog().All.Select(b => b with { ContinuityVerified = true, ReferenceFramingVerified = true, NewSubmissionCutoffUtc = null }));
        internal static ResolvedMedia Image(int width, int height)
        {
            using var bitmap = new Bitmap(width, height);
            using var stream = new MemoryStream();
            bitmap.Save(stream, ImageFormat.Png);
            return new ResolvedMedia(stream.ToArray(), "image/png");
        }

        [Theory]
        [InlineData("veo-3.1-generate-preview", "fal-ai/veo3.1")]
        [InlineData("veo-3.1-fast-generate-preview", "fal-ai/veo3.1/fast")]
        [InlineData("veo-3.1-lite-generate-preview", "fal-ai/veo3.1/lite")]
        public void TierAndModeMappingIsExact(string google, string fal)
        {
            Assert.Equal(fal, VideoSubmissionCoordinator.FalModelFor(google));
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = TestVideoFixtures.DefaultT2vRequest(model: google, mode: VideoMode.I2V, startFrame: source);
            var binding = ActiveCatalog().Resolve(request, DateTimeOffset.UtcNow).Binding!;
            Assert.Equal(fal + "/image-to-video", binding.SubmitEndpoint);
            Assert.Equal(fal, binding.ModelId);
            Assert.NotNull(new FalVeoBindingCatalog().Resolve(request, DateTimeOffset.UtcNow).Error);
        }

        [Theory]
        [InlineData(1024, 1024, "16:9", false)]
        [InlineData(1281, 720, "16:9", false)]
        [InlineData(720, 1280, "16:9", false)]
        [InlineData(1280, 720, "16:9", true)]
        [InlineData(720, 1280, "9:16", true)]
        [InlineData(1264, 711, "16:9", false)]
        public void SquareAndNearRatioSourcesRejectWithoutBlockingGoogle(int width, int height, string aspect, bool compatible)
        {
            foreach (var model in new[] { "veo-3.1-generate-preview", "veo-3.1-fast-generate-preview", "veo-3.1-lite-generate-preview" })
            {
                var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
                var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(model: model, mode: VideoMode.I2V, aspect: aspect, startFrame: source), new JsonObject());
                var binding = ActiveCatalog().Resolve(intent.Request, DateTimeOffset.UtcNow).Binding!;
                var error = FalVeoCompatibility.Validate(intent, binding, new Dictionary<MediaRef, ResolvedMedia> { [source] = Image(width, height) });
                Assert.Equal(compatible, error is null);
                if (!compatible) Assert.Equal("start_frame", error!.Field);
                Assert.True(CapabilityValidator.Validate(VeoCapabilities.Models[model].Capability, intent.Request).Success);
            }
        }

        [Fact]
        public void AllInputsValidateBeforeFirstUpload()
        {
            var first = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var last = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.Interp, startFrame: first, endFrame: last), new JsonObject());
            var binding = ActiveCatalog().Resolve(intent.Request, DateTimeOffset.UtcNow).Binding!;
            Assert.Equal("end_frame", FalVeoCompatibility.Validate(intent, binding, new Dictionary<MediaRef, ResolvedMedia> { [first] = Image(1280, 720), [last] = Image(1024, 1024) })!.Field);
            var tooLarge = new byte[8_000_001];
            Assert.Equal("start_frame", FalVeoCompatibility.Validate(intent, binding, new Dictionary<MediaRef, ResolvedMedia> { [first] = new(tooLarge, "image/png"), [last] = Image(1280, 720) })!.Field);
        }

        [Fact]
        public void OrderedRepeatedReferencesSurviveTranslation()
        {
            var a = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var b = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-generate-preview", referenceFrames: new[] { a, b, a });
            var intent = VideoRequestIntent.Normalize(request, new JsonObject());
            var binding = ActiveCatalog().Resolve(request, DateTimeOffset.UtcNow).Binding!;
            Assert.Null(FalVeoCompatibility.Validate(intent, binding, new Dictionary<MediaRef, ResolvedMedia> { [a] = Image(1280, 720), [b] = Image(1280, 720) }));
            Assert.Equal(new[] { a, b, a }, intent.Request.ReferenceFrames);
            Assert.NotNull(FalVeoCompatibility.Validate(VideoRequestIntent.Normalize(request.With(seed: 1), new JsonObject()), binding, new Dictionary<MediaRef, ResolvedMedia>()));
            Assert.NotNull(new FalVeoOptionsCodec().Deserialize(new JsonObject { ["person_generation"] = "allow_all" }).Error);
        }
    }
}
