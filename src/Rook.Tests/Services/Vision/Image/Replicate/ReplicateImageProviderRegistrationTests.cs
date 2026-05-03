using System.Linq;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Replicate;
using Rook.Tests.Services.Vision.Image;
using Xunit;

namespace Rook.Tests.Services.Vision.Image.Replicate
{
    public class ReplicateImageProviderRegistrationTests
    {
        [Fact]
        public void Registration_exposes_only_flux_schnell_model()
        {
            var registration = new ReplicateImageProviderRegistration(
                new FakeImageProvider());

            Assert.Equal("replicate", registration.ProviderName);
            var model = Assert.Single(registration.Models);
            Assert.Equal("black-forest-labs/flux-schnell", model.Key);
            Assert.Equal(ReplicateImageCapabilities.FluxSchnell, model.Value.Capability.Id);
            Assert.Equal("FLUX.1 Schnell", model.Value.Capability.Name);
            Assert.Equal("available", model.Value.Capability.Status);
            Assert.Equal(new[] { "1K" }, model.Value.Capability.Resolutions);
            Assert.Equal(new[] { "1:1", "4:3", "3:4", "16:9", "9:16" }, model.Value.Capability.AspectRatios);
            Assert.Equal(0, model.Value.Capability.MaxReferenceImages);
            Assert.True(model.Value.Capability.SupportsTextToImage);
            Assert.False(model.Value.Capability.SupportsImageToImage);
            Assert.IsType<ReplicateImagePricingModel>(model.Value.PricingModel);
        }

        [Fact]
        public void Registration_declares_replicate_api_token_requirement()
        {
            var registration = new ReplicateImageProviderRegistration(
                new FakeImageProvider());

            var requirement = Assert.Single(registration.SecretRequirements);
            Assert.Equal(GenerationSecretKeys.ReplicateApiToken, requirement.Key);
            Assert.Equal("Replicate API token", requirement.DisplayName);
            Assert.True(requirement.IsRequired);
            Assert.True(requirement.IsSensitive);
        }

        [Fact]
        public void Registration_declares_async_image_job_submission_mode()
        {
            var registration = new ReplicateImageProviderRegistration(
                new FakeImageProvider());

            Assert.Equal(ImageSubmissionMode.AsyncImageJob, registration.SubmissionMode);
        }

        [Fact]
        public void Injected_registry_resolves_only_replicate_flux_schnell()
        {
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new ReplicateImageProviderRegistration(new FakeImageProvider()),
            });

            Assert.True(registry.TryResolve(ReplicateImageCapabilities.FluxSchnell, out var resolved));
            Assert.Equal(ReplicateImageCapabilities.FluxSchnell, resolved.ModelId);
            Assert.Equal("replicate", resolved.ProviderName);
            Assert.False(registry.TryResolve("replicate/other-model", out _));

            var all = registry.EnumerateAllModels().ToArray();
            var descriptor = Assert.Single(all);
            Assert.Equal(ReplicateImageCapabilities.FluxSchnell, descriptor.ModelId);
            Assert.Equal("replicate", descriptor.ProviderName);
        }
    }
}
