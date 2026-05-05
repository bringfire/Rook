using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Fal
{
    public sealed class FalImageProviderRegistrationTests
    {
        [Fact]
        public void ProviderName_ReturnsFal()
        {
            var registration = new FalImageProviderRegistration(new FakeImageProvider());

            Assert.Equal("fal", registration.ProviderName);
        }

        [Fact]
        public void SecretRequirements_ExposeRequiredFalApiKey()
        {
            var registration = new FalImageProviderRegistration(new FakeImageProvider());

            var requirement = Assert.Single(registration.SecretRequirements);
            Assert.Equal(GenerationSecretKeys.FalApiKey, requirement.Key);
            Assert.Equal("fal API key", requirement.DisplayName);
            Assert.True(requirement.IsRequired);
            Assert.True(requirement.IsSensitive);
        }

        [Fact]
        public void Models_ExposeFluxSchnellCapability()
        {
            var registration = new FalImageProviderRegistration(new FakeImageProvider());

            Assert.True(registration.Models.ContainsKey(FalImageCapabilities.FluxSchnell));
            var model = registration.Models[FalImageCapabilities.FluxSchnell];
            Assert.Equal(FalImageCapabilities.FluxSchnell, model.Capability.Id);
            Assert.IsType<FalFluxSchnellPricingModel>(model.PricingModel);
        }

        [Fact]
        public void Models_ExposeGptImage2EditCapability()
        {
            var registration = new FalImageProviderRegistration(new FakeImageProvider());

            Assert.True(registration.Models.ContainsKey(FalImageCapabilities.GptImage2Edit));
            var model = registration.Models[FalImageCapabilities.GptImage2Edit];
            Assert.Equal("GPT Image 2 Edit", model.Capability.Name);
            Assert.Equal(new[] { "auto" }, model.Capability.Resolutions);
            Assert.Equal(new[] { "match_input_image" }, model.Capability.AspectRatios);
            Assert.Equal(0, model.Capability.MaxReferenceImages);
            Assert.True(model.Capability.SupportsImageToImage);
            Assert.False(model.Capability.SupportsTextToImage);
        }

        [Fact]
        public void GetSubmissionMode_ReturnsAsyncForGptImage2EditAndSyncForSchnell()
        {
            var registration = new FalImageProviderRegistration(new FakeImageProvider());

            Assert.Equal(
                ImageSubmissionMode.Sync,
                registration.GetSubmissionMode(FalImageCapabilities.FluxSchnell));
            Assert.Equal(
                ImageSubmissionMode.AsyncImageJob,
                registration.GetSubmissionMode(FalImageCapabilities.GptImage2Edit));
        }

        private sealed class FakeImageProvider : IImageProvider
        {
            public string ProviderName => FalImageCapabilities.ProviderName;

            public Task<ProviderSubmitOutcome> SubmitAsync(
                ImageGenerationRequest request,
                IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
                CancellationToken ct) =>
                throw new NotImplementedException();

            public Task<ProviderStatusOutcome> GetStatusAsync(
                ProviderJobHandle handle,
                CancellationToken ct) =>
                throw new NotImplementedException();

            public Task<ProviderCancelOutcome> CancelAsync(
                ProviderJobHandle handle,
                CancellationToken ct) =>
                throw new NotImplementedException();

            public Task<ProviderResultOutcome> FetchResultAsync(
                ProviderJobHandle handle,
                CancellationToken ct) =>
                throw new NotImplementedException();
        }
    }
}
