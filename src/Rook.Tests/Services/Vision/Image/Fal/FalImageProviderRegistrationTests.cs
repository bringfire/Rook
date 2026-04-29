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

            var model = Assert.Single(registration.Models);
            Assert.Equal(FalImageCapabilities.FluxSchnell, model.Key);
            Assert.Equal(FalImageCapabilities.FluxSchnell, model.Value.Capability.Id);
            Assert.IsType<FalFluxSchnellPricingModel>(model.Value.PricingModel);
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
