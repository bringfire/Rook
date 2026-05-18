using System;
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
        public void Registration_exposes_curated_replicate_models()
        {
            var registration = new ReplicateImageProviderRegistration(
                new FakeImageProvider());

            Assert.Equal("replicate", registration.ProviderName);

            var models = registration.Models;
            Assert.Equal(2, models.Count);

            var schnell = models[ReplicateImageCapabilities.FluxSchnell];
            Assert.Equal(ReplicateImageCapabilities.FluxSchnell, schnell.Capability.Id);
            Assert.Equal("FLUX.1 Schnell", schnell.Capability.Name);
            Assert.Equal("available", schnell.Capability.Status);
            Assert.Equal(new[] { "1K" }, schnell.Capability.Resolutions);
            Assert.Equal(new[] { "1:1", "4:3", "3:4", "16:9", "9:16" }, schnell.Capability.AspectRatios);
            Assert.Equal(0, schnell.Capability.MaxReferenceImages);
            Assert.True(schnell.Capability.SupportsTextToImage);
            Assert.False(schnell.Capability.SupportsImageToImage);
            Assert.IsType<ReplicateImagePricingModel>(schnell.PricingModel);

            var flux2 = models[ReplicateImageCapabilities.Flux2Pro];
            Assert.Equal(ReplicateImageCapabilities.Flux2Pro, flux2.Capability.Id);
            Assert.Equal("FLUX.2 Pro", flux2.Capability.Name);
            Assert.Equal("available", flux2.Capability.Status);
            Assert.Equal(new[] { "1 MP", "2 MP", "4 MP" }, flux2.Capability.Resolutions);
            Assert.Equal(
                new[] { "1:1", "4:3", "3:4", "16:9", "9:16", "match_input_image" },
                flux2.Capability.AspectRatios);
            Assert.Equal(0, flux2.Capability.MaxReferenceImages);
            Assert.True(flux2.Capability.SupportsTextToImage);
            Assert.True(flux2.Capability.SupportsImageToImage);
            Assert.Equal(8, ReplicateImageCapabilities.Flux2ProMediaPolicy.Model.MaxInputImages);
            Assert.IsType<ReplicateImagePricingModel>(flux2.PricingModel);
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
        public void Injected_registry_resolves_curated_replicate_models()
        {
            var registry = new DefaultImageProviderRegistry(new IImageProviderRegistration[]
            {
                new ReplicateImageProviderRegistration(new FakeImageProvider()),
            });

            Assert.True(registry.TryResolve(ReplicateImageCapabilities.FluxSchnell, out var schnell));
            Assert.Equal(ReplicateImageCapabilities.FluxSchnell, schnell.ModelId);
            Assert.Equal("replicate", schnell.ProviderName);

            Assert.True(registry.TryResolve(ReplicateImageCapabilities.Flux2Pro, out var flux2));
            Assert.Equal(ReplicateImageCapabilities.Flux2Pro, flux2.ModelId);
            Assert.Equal("replicate", flux2.ProviderName);
            Assert.True(flux2.Capability.SupportsImageToImage);
            Assert.True(flux2.Capability.SupportsTextToImage);

            Assert.False(registry.TryResolve("replicate/other-model", out _));

            var all = registry.EnumerateAllModels()
                .OrderBy(d => d.ModelId, StringComparer.Ordinal)
                .ToArray();
            Assert.Equal(2, all.Length);
            Assert.Contains(all, d => d.ModelId == ReplicateImageCapabilities.FluxSchnell);
            Assert.Contains(all, d => d.ModelId == ReplicateImageCapabilities.Flux2Pro);
        }
    }
}
