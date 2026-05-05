using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalSeedanceI2vSourcePayloadTests
    {
        [Fact]
        public void FromResolvedMedia_i2v_requires_start_frame()
        {
            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(VideoMode.I2V, startFrame: null),
                EmptyMedia());

            Assert.Null(payload);
            AssertInvalid(error, "start_frame");
        }

        [Fact]
        public void FromResolvedMedia_interp_requires_start_frame()
        {
            var end = Artifact(VideoMediaRoles.EndFrame);

            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(VideoMode.Interp, startFrame: null, endFrame: end),
                Media(end, JpegBytes(), "image/jpeg"));

            Assert.Null(payload);
            AssertInvalid(error, "start_frame");
        }

        [Fact]
        public void FromResolvedMedia_interp_requires_end_frame()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);

            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(VideoMode.Interp, startFrame: start, endFrame: null),
                Media(start, PngBytes(), "image/png"));

            Assert.Null(payload);
            AssertInvalid(error, "end_frame");
        }

        [Fact]
        public void FromResolvedMedia_i2v_builds_start_data_uri_with_detected_mime()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);
            var bytes = PngBytes();

            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(VideoMode.I2V, startFrame: start),
                Media(start, bytes, "image/png"));

            Assert.Null(error);
            Assert.NotNull(payload);
            Assert.Equal(
                "data:image/png;base64," + Convert.ToBase64String(bytes),
                payload!.ImageUrl);
            Assert.Null(payload.EndImageUrl);
        }

        [Fact]
        public void FromResolvedMedia_i2v_builds_webp_start_data_uri()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);
            var bytes = WebPBytes();

            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(VideoMode.I2V, startFrame: start),
                Media(start, bytes, "image/webp"));

            Assert.Null(error);
            Assert.NotNull(payload);
            Assert.Equal(
                "data:image/webp;base64," + Convert.ToBase64String(bytes),
                payload!.ImageUrl);
            Assert.Null(payload.EndImageUrl);
        }

        [Fact]
        public void FromResolvedMedia_interp_builds_start_and_end_data_uris()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);
            var end = Artifact(VideoMediaRoles.EndFrame);
            var startBytes = PngBytes();
            var endBytes = JpegBytes();

            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(VideoMode.Interp, startFrame: start, endFrame: end),
                Media(
                    (start, new ResolvedMedia(startBytes, "image/png")),
                    (end, new ResolvedMedia(endBytes, "image/jpeg"))));

            Assert.Null(error);
            Assert.NotNull(payload);
            Assert.Equal(
                "data:image/png;base64," + Convert.ToBase64String(startBytes),
                payload!.ImageUrl);
            Assert.Equal(
                "data:image/jpeg;base64," + Convert.ToBase64String(endBytes),
                payload.EndImageUrl);
        }

        [Fact]
        public void FromResolvedMedia_rejects_reference_frames()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);
            var reference = Artifact("reference");

            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(
                    VideoMode.I2V,
                    startFrame: start,
                    referenceFrames: new[] { reference }),
                Media(
                    (start, new ResolvedMedia(PngBytes(), "image/png")),
                    (reference, new ResolvedMedia(JpegBytes(), "image/jpeg"))));

            Assert.Null(payload);
            AssertInvalid(error, "reference_frames");
        }

        [Fact]
        public void FromResolvedMedia_rejects_declared_mime_mismatch()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);

            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(VideoMode.I2V, startFrame: start),
                Media(start, PngBytes(), "image/jpeg"));

            Assert.Null(payload);
            AssertInvalid(error, "start_frame");
        }

        [Fact]
        public void FromResolvedMedia_rejects_unsupported_image_bytes()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);

            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(VideoMode.I2V, startFrame: start),
                Media(start, GifBytes(), "image/gif"));

            Assert.Null(payload);
            AssertInvalid(error, "start_frame");
        }

        [Fact]
        public void FromResolvedMedia_rejects_oversized_source()
        {
            var start = Artifact(VideoMediaRoles.StartFrame);
            var bytes = PngBytes();
            Array.Resize(ref bytes, (int)FalSeedanceI2vSourcePayload.MaxRawBytes + 1);

            var (payload, error) = FalSeedanceI2vSourcePayload.FromResolvedMedia(
                Request(VideoMode.I2V, startFrame: start),
                Media(start, bytes, "image/png"));

            Assert.Null(payload);
            AssertInvalid(error, "start_frame");
        }

        private static VideoGenerationRequest Request(
            VideoMode mode,
            MediaRef? startFrame,
            MediaRef? endFrame = null,
            IReadOnlyList<MediaRef>? referenceFrames = null) =>
            new(
                Model: FalVideoCapabilities.SeedanceI2v,
                Mode: mode,
                DurationSeconds: 6,
                Resolution: "720p",
                AspectRatio: "16:9",
                Prompt: "clip",
                StartFrame: startFrame,
                EndFrame: endFrame,
                ReferenceFrames: referenceFrames,
                Seed: null,
                Options: new FalVideoOptions(),
                NumberOfVideos: 1);

        private static MediaRef Artifact(string role) =>
            MediaRef.ForArtifact(Guid.NewGuid(), role);

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> EmptyMedia() =>
            new Dictionary<MediaRef, ResolvedMedia>();

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> Media(
            MediaRef mediaRef,
            byte[] bytes,
            string mimeType) =>
            new Dictionary<MediaRef, ResolvedMedia>
            {
                [mediaRef] = new ResolvedMedia(bytes, mimeType),
            };

        private static IReadOnlyDictionary<MediaRef, ResolvedMedia> Media(
            params (MediaRef Ref, ResolvedMedia Media)[] entries)
        {
            var media = new Dictionary<MediaRef, ResolvedMedia>();
            foreach (var entry in entries)
                media[entry.Ref] = entry.Media;

            return media;
        }

        private static void AssertInvalid(GenerationError? error, string field)
        {
            Assert.NotNull(error);
            Assert.Equal(GenerationErrorCode.InvalidRequest, error!.Code);
            Assert.False(error.Retryable);
            Assert.Equal(field, error.Field);
        }

        private static byte[] PngBytes() =>
            new byte[]
            {
                0x89, 0x50, 0x4E, 0x47,
                0x0D, 0x0A, 0x1A, 0x0A,
                1, 2, 3, 4,
            };

        private static byte[] JpegBytes() =>
            new byte[] { 0xFF, 0xD8, 0xFF, 1, 2, 3 };

        private static byte[] WebPBytes() =>
            new byte[]
            {
                0x52, 0x49, 0x46, 0x46,
                0x10, 0x00, 0x00, 0x00,
                0x57, 0x45, 0x42, 0x50,
                1, 2, 3, 4,
            };

        private static byte[] GifBytes() =>
            new byte[] { 0x47, 0x49, 0x46, 0x38, 1, 2, 3 };
    }
}
