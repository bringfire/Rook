using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;
using Xunit;

namespace Rook.Tests.Services.Vision.Video.Fal
{
    public class FalVideoProviderRegistrationTests
    {
        [Fact]
        public void Registration_exposes_single_wan_t2v_model()
        {
            var registration = new FalVideoProviderRegistration(new NullVideoProvider());

            var model = Assert.Single(registration.Models);
            Assert.Equal(FalVideoCapabilities.WanT2v, model.Key);
            Assert.Equal(FalVideoCapabilities.WanT2v, model.Value.Capability.Id);
            Assert.IsType<FalWanT2vPricingModel>(model.Value.PricingModel);
            Assert.IsType<FalVideoOptionsCodec>(registration.OptionsCodec);
        }

        [Fact]
        public void Capability_is_t2v_only_with_no_reference_images()
        {
            var cap = FalVideoCapabilities.Models[FalVideoCapabilities.WanT2v].Capability;

            Assert.Equal(new[] { VideoMode.T2V }, cap.Modes);
            Assert.False(cap.SupportsReferenceImages);
            Assert.Equal(0, cap.MaxReferenceImages);
            Assert.Empty(cap.Must8sWith);
            Assert.Contains("720p", cap.Resolutions);
            Assert.Contains("1080p", cap.Resolutions);
            Assert.Contains(2, cap.Durations);
            Assert.Contains(15, cap.Durations);
        }

        [Fact]
        public void Capability_uses_current_plan_aspect_ratios()
        {
            var cap = FalVideoCapabilities.Models[FalVideoCapabilities.WanT2v].Capability;

            Assert.Equal(
                new[] { "16:9", "9:16", "1:1", "4:3", "3:4" }.OrderBy(x => x),
                cap.AspectRatios.OrderBy(x => x));
        }

        [Fact]
        public void Secret_requirements_use_fal_api_key()
        {
            var registration = new FalVideoProviderRegistration(new NullVideoProvider());

            var requirement = Assert.Single(registration.SecretRequirements);
            Assert.Equal(GenerationSecretKeys.FalApiKey, requirement.Key);
            Assert.True(requirement.IsRequired);
        }

        private sealed class NullVideoProvider : IVideoProvider
        {
            public string ProviderName => FalVideoCapabilities.ProviderName;

            public Task<ProviderSubmitOutcome> SubmitAsync(
                VideoGenerationRequest request,
                IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia,
                CancellationToken ct) =>
                throw new NotSupportedException();

            public Task<ProviderStatusOutcome> GetStatusAsync(
                ProviderJobHandle handle,
                CancellationToken ct) =>
                throw new NotSupportedException();

            public Task<ProviderCancelOutcome> CancelAsync(
                ProviderJobHandle handle,
                CancellationToken ct) =>
                throw new NotSupportedException();

            public Task<ProviderResultOutcome> FetchResultAsync(
                ProviderJobHandle handle,
                CancellationToken ct) =>
                throw new NotSupportedException();
        }
    }
}
