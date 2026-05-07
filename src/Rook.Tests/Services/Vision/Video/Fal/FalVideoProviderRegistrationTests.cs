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
        public void Registration_exposes_wan_t2v_seedance_i2v_and_kling_i2v_models()
        {
            var registration = new FalVideoProviderRegistration(new NullVideoProvider());

            Assert.Equal(3, registration.Models.Count);
            Assert.True(registration.Models.ContainsKey(FalVideoCapabilities.WanT2v));
            Assert.True(registration.Models.ContainsKey(FalVideoCapabilities.SeedanceI2v));
            Assert.True(registration.Models.ContainsKey(FalVideoCapabilities.KlingV3StandardI2v));
            Assert.Equal(
                FalVideoCapabilities.WanT2v,
                registration.Models[FalVideoCapabilities.WanT2v].Capability.Id);
            Assert.Equal(
                FalVideoCapabilities.SeedanceI2v,
                registration.Models[FalVideoCapabilities.SeedanceI2v].Capability.Id);
            Assert.Equal(
                FalVideoCapabilities.KlingV3StandardI2v,
                registration.Models[FalVideoCapabilities.KlingV3StandardI2v].Capability.Id);
            Assert.IsType<FalWanT2vPricingModel>(
                registration.Models[FalVideoCapabilities.WanT2v].PricingModel);
            Assert.IsType<FalSeedanceI2vPricingModel>(
                registration.Models[FalVideoCapabilities.SeedanceI2v].PricingModel);
            Assert.IsType<FalKlingV3StandardI2vPricingModel>(
                registration.Models[FalVideoCapabilities.KlingV3StandardI2v].PricingModel);
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
        public void Seedance_capability_is_i2v_interp_without_reference_images()
        {
            var cap = FalVideoCapabilities.Models[FalVideoCapabilities.SeedanceI2v].Capability;

            Assert.Equal("bytedance/seedance-2.0/image-to-video", cap.Id);
            Assert.Equal("Seedance 2.0 Image to Video", cap.Name);
            Assert.Equal(
                new[] { VideoMode.I2V, VideoMode.Interp }.OrderBy(x => x),
                cap.Modes.OrderBy(x => x));
            Assert.DoesNotContain(VideoMode.T2V, cap.Modes);
            Assert.False(cap.SupportsReferenceImages);
            Assert.Equal(0, cap.MaxReferenceImages);
            Assert.Empty(cap.Must8sWith);
            Assert.Contains("480p", cap.Resolutions);
            Assert.Contains("720p", cap.Resolutions);
            Assert.Contains("1080p", cap.Resolutions);
            Assert.Equal(Enumerable.Range(4, 12), cap.Durations);
            Assert.DoesNotContain(0, cap.Durations);
            Assert.Contains("16:9", cap.AspectRatios);
            Assert.Contains("9:16", cap.AspectRatios);
        }

        [Fact]
        public void Kling_capability_is_i2v_interp_with_auto_shape_and_3_to_15_durations()
        {
            var cap = FalVideoCapabilities.Models[FalVideoCapabilities.KlingV3StandardI2v].Capability;

            Assert.Equal("fal-ai/kling-video/v3/standard/image-to-video", cap.Id);
            Assert.Equal("Kling v3 Standard Image to Video", cap.Name);
            Assert.Equal("preview", cap.Status);
            Assert.Equal(new[] { VideoMode.I2V, VideoMode.Interp }, cap.Modes);
            Assert.DoesNotContain(VideoMode.T2V, cap.Modes);
            Assert.False(cap.SupportsReferenceImages);
            Assert.Equal(0, cap.MaxReferenceImages);
            Assert.Empty(cap.Must8sWith);
            Assert.Equal(new[] { "auto" }, cap.Resolutions);
            Assert.Equal(new[] { "auto" }, cap.AspectRatios);
            Assert.Equal(Enumerable.Range(3, 13), cap.Durations);
            Assert.DoesNotContain(2, cap.Durations);
            Assert.DoesNotContain(16, cap.Durations);
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
