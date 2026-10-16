using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Rook.Services.Vision.Video.Framing;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVeoCompatibilityTests
    {
        [Fact]
        public async Task OmittedFramingPreservesLegacyApngWhileExplicitInspectionRejectsAnimation()
        {
            var png = File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("matching.png"));
            using var output = new MemoryStream(); output.Write(png, 0, 33);
            void Big(Stream stream, uint n) { stream.WriteByte((byte)(n >> 24)); stream.WriteByte((byte)(n >> 16)); stream.WriteByte((byte)(n >> 8)); stream.WriteByte((byte)n); }
            void Chunk(string tag, byte[] payload)
            {
                var name = System.Text.Encoding.ASCII.GetBytes(tag); Big(output, (uint)payload.Length); output.Write(name, 0, 4); output.Write(payload, 0, payload.Length);
                uint crc = uint.MaxValue;
                foreach (byte b in name.Concat(payload)) { crc ^= b; for (int n = 0; n < 8; n++) crc = (crc & 1) == 0 ? crc >> 1 : 0xedb88320 ^ (crc >> 1); }
                Big(output, crc ^ uint.MaxValue);
            }
            Chunk("acTL", new byte[] { 0, 0, 0, 1, 0, 0, 0, 0 });
            using var frame = new MemoryStream(); foreach (uint value in new uint[] { 0, 1280, 720, 0, 0 }) Big(frame, value);
            frame.Write(new byte[] { 0, 1, 0, 10, 0, 0 }, 0, 6); Chunk("fcTL", frame.ToArray());
            output.Write(png, 33, png.Length - 33); var bytes = output.ToArray();
            var reference = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = TestVideoFixtures.DefaultT2vRequest(model: "fal-ai/veo3.1", mode: VideoMode.I2V, resolution: "720p", startFrame: reference).With(options: new FalVeoOptions());
            var intent = VideoRequestIntent.Normalize(request, new JsonObject());
            var binding = new FalVeoBindingCatalog().GetCandidate(request).Binding!;
            using var original = VideoFrozenBuffer.CopyOf(bytes, new VideoBufferBudget());
            Assert.Equal("source_animation_unsupported", VideoStillImageInspector.Inspect(original, "start_frame").Error!.ProviderErrorCode);
            Assert.Null(FalVeoCompatibility.ValidateMetadata(intent, binding, new Dictionary<MediaRef, ResolvedMedia> { [reference] = new(bytes, "image/png") }));
            using var webp = VideoFrozenBuffer.CopyOf(File.ReadAllBytes(VideoStillImageInspectorTests.Fixture("animated.webp")), new VideoBufferBudget());
            Assert.Equal("source_animation_unsupported", VideoStillImageInspector.Inspect(webp, "start_frame", allowLegacyPngAnimation: true).Error!.ProviderErrorCode);
            using var rig = new VideoFramingQuoteTests.Rig();
            var source = rig.Store.Create("generated_image", new[] { new BlobInput("image", bytes, "png") });
            var preview = await rig.Preparation.PreviewAsync(new(rig.Intent.Request.Model, VideoMode.I2V,
                new[] { new VideoFramingSourceSlot("start_frame", MediaRef.ForArtifact(source.Id, "image")) }, "720p", "16:9"), default);
            Assert.Equal("source_animation_unsupported", preview.Fit!.Error!.ProviderErrorCode);
            Assert.Equal("source_animation_unsupported", preview.Fill!.Error!.ProviderErrorCode);
            Assert.Equal(0, rig.Cache.BundleCount);
        }
        internal static FalVeoBindingCatalog ActiveCatalog() => new(new FalVeoBindingCatalog().All.Select(b => b with { SubmissionVerified = true, ReferenceFramingVerified = true, NewSubmissionCutoffUtc = null }));
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
            Assert.Null(new FalVeoBindingCatalog().Resolve(request, DateTimeOffset.UtcNow).Error);
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
                var error = FalVeoCompatibility.ValidateMetadata(intent, binding, new Dictionary<MediaRef, ResolvedMedia> { [source] = Image(width, height) });
                Assert.Equal(compatible, error is null);
                if (!compatible) { Assert.Equal("source_framing", error!.Field); Assert.Equal("framing_choice_required", error.ProviderErrorCode); }
                Assert.True(CapabilityValidator.Validate(VeoCapabilities.Models[model].Capability, intent.Request).Success);
            }
        }

        [Fact]
        public void TruncatedImageHeaderIsNotAnUploadableSource()
        {
            var source = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-generate-preview", mode: VideoMode.I2V, startFrame: source), new JsonObject());
            var header = Image(1280, 720).Bytes.Take(24).ToArray();
            Assert.NotNull(FalVeoCompatibility.ValidateMetadata(intent, ActiveCatalog().GetCandidate(intent.Request).Binding!, new Dictionary<MediaRef, ResolvedMedia> { [source] = new(header, "image/png") }));
        }
        [Fact]
        public void AllInputsValidateBeforeFirstUpload()
        {
            var first = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var last = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var intent = VideoRequestIntent.Normalize(TestVideoFixtures.DefaultT2vRequest(mode: VideoMode.Interp, startFrame: first, endFrame: last), new JsonObject());
            var binding = ActiveCatalog().Resolve(intent.Request, DateTimeOffset.UtcNow).Binding!;
            Assert.Equal("framing_choice_required", FalVeoCompatibility.ValidateMetadata(intent, binding, new Dictionary<MediaRef, ResolvedMedia> { [first] = Image(1280, 720), [last] = Image(1024, 1024) })!.ProviderErrorCode);
            var tooLarge = new byte[8_000_001];
            Assert.Equal("start_frame", FalVeoCompatibility.ValidateMetadata(intent, binding, new Dictionary<MediaRef, ResolvedMedia> { [first] = new(tooLarge, "image/png"), [last] = Image(1280, 720) })!.Field);
        }

        [Fact]
        public void OrderedRepeatedReferencesSurviveTranslation()
        {
            var a = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var b = MediaRef.ForArtifact(Guid.NewGuid(), "image");
            var request = TestVideoFixtures.DefaultT2vRequest(model: "veo-3.1-generate-preview", referenceFrames: new[] { a, b, a });
            var intent = VideoRequestIntent.Normalize(request, new JsonObject());
            var binding = ActiveCatalog().Resolve(request, DateTimeOffset.UtcNow).Binding!;
            Assert.Null(FalVeoCompatibility.ValidateMetadata(intent, binding, new Dictionary<MediaRef, ResolvedMedia> { [a] = Image(1280, 720), [b] = Image(1280, 720) }));
            Assert.Equal(new[] { a, b, a }, intent.Request.ReferenceFrames);
            Assert.NotNull(FalVeoCompatibility.ValidateMetadata(VideoRequestIntent.Normalize(request.With(seed: 1), new JsonObject()), binding, new Dictionary<MediaRef, ResolvedMedia>()));
            Assert.NotNull(new FalVeoOptionsCodec().Deserialize(new JsonObject { ["person_generation"] = "allow_all" }).Error);
        }
    }
}
