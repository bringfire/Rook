using System;
using System.Collections.Generic;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Gemini;
using Rook.Services.Vision.Image.Jobs;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Jobs
{
    public class ImageJobResultTypesTests
    {
        [Fact]
        public void SubmitOk_requires_non_empty_job_id()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobSubmitResult.Ok(Guid.Empty, ImageJobState.Queued));
        }

        [Fact]
        public void StatusComplete_requires_artifact_id()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobStatusResult.Complete(Guid.Empty));
        }

        [Fact]
        public void StatusInFlight_rejects_undefined_state()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobStatusResult.InFlight((ImageJobState)999, null));
        }

        [Fact]
        public void StatusFailed_requires_terminal_failure_state()
        {
            var error = new GenerationError(
                GenerationErrorCode.ExecutionFailed,
                "failed",
                Retryable: true);

            Assert.Throws<ArgumentException>(() =>
                ImageJobStatusResult.Failed(ImageJobState.Polling, error));
        }

        [Fact]
        public void FetchComplete_requires_files()
        {
            Assert.Throws<ArgumentException>(() =>
                ImageJobFetchResult.Complete(
                    Guid.NewGuid(),
                    Array.Empty<ImageJobResultFile>()));
        }

        [Fact]
        public void Record_constructor_allows_optional_job_details()
        {
            var jobId = Guid.NewGuid();
            var updatedAt = DateTimeOffset.UtcNow;

            var record = new ImageJobRecord(
                jobId,
                ImageJobState.Queued,
                "model",
                "provider",
                updatedAt);

            Assert.Equal(jobId, record.JobId);
            Assert.Equal(ImageJobState.Queued, record.State);
            Assert.Equal("model", record.Model);
            Assert.Equal("provider", record.Provider);
            Assert.Equal(updatedAt, record.UpdatedAt);
            Assert.Null(record.ProviderHandle);
            Assert.Null(record.ResultArtifactId);
            Assert.Null(record.Error);
        }

        [Fact]
        public void StartRequest_three_arg_constructor_defaults_resolved_model_to_null()
        {
            var request = Request(GeminiImageCapabilities.DefaultModel);

            var start = new ImageJobStartRequest(
                request,
                new Dictionary<MediaRef, ResolvedMedia>(),
                Array.Empty<Guid>());

            Assert.Same(request, start.Request);
            Assert.Null(start.ResolvedModel);
        }

        [Fact]
        public void StartRequest_can_carry_explicit_resolved_model()
        {
            var request = Request("gemini-future-image-preview");
            var provider = new FakeImageProvider();
            var resolvedModel = SyntheticResolvedModel(provider, request.Model);

            var start = new ImageJobStartRequest(
                request,
                new Dictionary<MediaRef, ResolvedMedia>(),
                Array.Empty<Guid>(),
                resolvedModel);

            Assert.Same(resolvedModel, start.ResolvedModel);
        }

        private static ImageGenerationRequest Request(string model) =>
            new(
                Model: model,
                Prompt: "red cube",
                Resolution: "1K",
                AspectRatio: "",
                NumberOfImages: 1,
                ReferenceImages: null,
                Options: new GeminiImageOptions());

        private static ResolvedImageModel SyntheticResolvedModel(
            IImageProvider provider,
            string model) =>
            new(
                ModelId: model,
                ProviderName: GeminiImageCapabilities.ProviderName,
                Provider: provider,
                Capability: new ImageCapability(
                    Id: model,
                    Name: model,
                    Status: "preview",
                    Resolutions: new[] { "1K" },
                    AspectRatios: new[] { "1:1" },
                    MaxReferenceImages: 0,
                    SupportsImageToImage: true,
                    SupportsTextToImage: true),
                PricingModel: new GeminiImagePricingModel(),
                OptionsCodec: new GeminiImageOptionsCodec());
    }
}
