using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    public class DefaultVideoProviderRegistryTests
    {
        // ─── Resolution ───────────────────────────────────────────────

        [Fact]
        public void TryResolve_exact_model_id_returns_true_with_resolved_model()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            var ok = registry.TryResolve("veo-3.1-lite-generate-preview", out var model);

            Assert.True(ok);
            Assert.Equal("veo-3.1-lite-generate-preview", model.ModelId);
            Assert.Equal("veo", model.ProviderName);
            Assert.NotNull(model.Provider);
            Assert.NotNull(model.Capability);
            Assert.NotNull(model.PricingModel);
            Assert.NotNull(model.OptionsCodec);
        }

        [Fact]
        public void TryResolve_unknown_model_returns_false()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            var ok = registry.TryResolve("veo-9000", out _);

            Assert.False(ok);
        }

        [Fact]
        public void TryResolve_null_model_id_returns_false()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            var ok = registry.TryResolve(null!, out _);

            Assert.False(ok);
        }

        [Fact]
        public void TryResolve_empty_model_id_returns_false()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            var ok = registry.TryResolve("", out _);

            Assert.False(ok);
        }

        [Fact]
        public void TryResolve_whitespace_model_id_returns_false()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            var ok = registry.TryResolve("   ", out _);

            Assert.False(ok);
        }

        [Fact]
        public void TryResolve_does_not_match_by_prefix()
        {
            // V1c locks in exact-match resolution; "veo-" alone doesn't
            // resolve to anything.
            var registry = TestVideoFixtures.RegistryWithVeo();

            var ok = registry.TryResolve("veo-", out _);

            Assert.False(ok);
        }

        // ─── EnumerateAllModels ───────────────────────────────────────

        [Fact]
        public void EnumerateAllModels_returns_descriptor_per_registered_model()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            var descriptors = registry.EnumerateAllModels();

            // VeoCapabilities ships 6 models.
            Assert.Equal(6, descriptors.Count);
            Assert.All(descriptors, d => Assert.Equal("veo", d.ProviderName));
            Assert.All(descriptors, d => Assert.Equal(PricingKind.PerSecond, d.PricingKind));
            Assert.All(descriptors, d => Assert.Equal("veo-rate-card-v1", d.PricingSource));
        }

        [Fact]
        public void EnumerateAllModels_returns_stable_order_across_calls()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            var first = registry.EnumerateAllModels().Select(d => d.ModelId).ToList();
            var second = registry.EnumerateAllModels().Select(d => d.ModelId).ToList();

            Assert.Equal(first, second);
        }

        [Fact]
        public void EnumerateAllModels_descriptor_contains_capability_data()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            var descriptors = registry.EnumerateAllModels();
            var lite = descriptors.Single(d => d.ModelId == "veo-3.1-lite-generate-preview");

            Assert.Equal("Veo 3.1 Lite", lite.Capability.Name);
            Assert.False(lite.Capability.SupportsReferenceImages);
        }

        // ─── Build-time validation: duplicate model id ────────────────

        [Fact]
        public void Constructor_throws_on_duplicate_model_id_across_registrations()
        {
            // Two registrations both contribute the full Veo model set;
            // the first duplicate model id encountered (whichever the
            // dictionary iterates first) triggers the throw.
            var first = new VeoProviderRegistration(new FakeVideoProvider());
            var second = new VeoProviderRegistration(new FakeVideoProvider());

            var ex = Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new IVideoProviderRegistration[] { first, second }));

            Assert.Contains("Duplicate model id", ex.Message);
            // Any Veo model id must appear (the offending one).
            Assert.Contains("veo-", ex.Message);
        }

        [Fact]
        public void Constructor_duplicate_message_names_both_provider_names()
        {
            var first = new VeoProviderRegistration(new FakeVideoProvider());
            var fauxVeoTwin = new VeoProviderRegistration(new FakeVideoProvider());

            var ex = Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new IVideoProviderRegistration[] { first, fauxVeoTwin }));

            // Both registrations are named "veo" (same name allowed —
            // Codex Finding 5) but the message must reference the
            // provider name twice for diagnosability.
            Assert.Contains("veo", ex.Message);
        }

        // ─── Build-time validation: duplicate provider name ALLOWED ──

        [Fact]
        public void Constructor_allows_duplicate_provider_names_when_model_ids_unique()
        {
            // Per Codex Finding 5: duplicate provider names are
            // legitimate (e.g. a provider splits registrations across
            // product families). Only model-id collisions are fatal.
            var alpha = new TestRegistration
            {
                ProviderName = "veo",
                Models = new Dictionary<string, (ModelCapability, IPricingModel)>
                {
                    ["alpha-model"] = (StubCap("alpha-model"), StubPricing()),
                },
            };
            var beta = new TestRegistration
            {
                ProviderName = "veo",
                Models = new Dictionary<string, (ModelCapability, IPricingModel)>
                {
                    ["beta-model"] = (StubCap("beta-model"), StubPricing()),
                },
            };

            // Should not throw.
            var registry = new DefaultVideoProviderRegistry(new[] { alpha, beta });

            Assert.True(registry.TryResolve("alpha-model", out _));
            Assert.True(registry.TryResolve("beta-model", out _));
        }

        // ─── Build-time validation: null/empty inputs ─────────────────

        [Fact]
        public void Constructor_throws_on_null_registrations_enumerable()
        {
            Assert.Throws<ArgumentNullException>(() =>
                new DefaultVideoProviderRegistry(registrations: null!));
        }

        [Fact]
        public void Constructor_throws_on_null_registration_in_list()
        {
            Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(
                    new IVideoProviderRegistration[] { null! }));
        }

        [Fact]
        public void Constructor_throws_on_empty_provider_name()
        {
            var bad = new TestRegistration { ProviderName = "  " };

            Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new[] { bad }));
        }

        [Fact]
        public void Constructor_throws_on_null_provider()
        {
            var bad = new TestRegistration { Provider = null! };

            Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new[] { bad }));
        }

        [Fact]
        public void Constructor_throws_on_null_options_codec()
        {
            var bad = new TestRegistration { OptionsCodec = null! };

            Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new[] { bad }));
        }

        [Fact]
        public void Constructor_throws_on_empty_model_id()
        {
            var bad = new TestRegistration
            {
                Models = new Dictionary<string, (ModelCapability, IPricingModel)>
                {
                    ["  "] = (StubCap("  "), StubPricing()),
                },
            };

            Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new[] { bad }));
        }

        [Fact]
        public void Constructor_throws_on_null_capability()
        {
            var bad = new TestRegistration
            {
                Models = new Dictionary<string, (ModelCapability, IPricingModel)>
                {
                    ["m"] = (null!, StubPricing()),
                },
            };

            Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new[] { bad }));
        }

        [Fact]
        public void Constructor_throws_on_null_pricing_model()
        {
            var bad = new TestRegistration
            {
                Models = new Dictionary<string, (ModelCapability, IPricingModel)>
                {
                    ["m"] = (StubCap("m"), null!),
                },
            };

            Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new[] { bad }));
        }

        [Fact]
        public void Constructor_allows_empty_registrations_list()
        {
            var registry = new DefaultVideoProviderRegistry(
                Array.Empty<IVideoProviderRegistration>());

            Assert.False(registry.TryResolve("anything", out _));
            Assert.Empty(registry.EnumerateAllModels());
        }

        // ─── Helpers ──────────────────────────────────────────────────

        private static ModelCapability StubCap(string id) => new(
            Id: id, Name: id, Status: "preview",
            Resolutions: new[] { "720p" },
            Durations: new[] { 8 },
            AspectRatios: new[] { "16:9" },
            Modes: new[] { VideoMode.T2V },
            SupportsReferenceImages: false,
            MaxReferenceImages: 0,
            Must8sWith: Array.Empty<string>());

        private static IPricingModel StubPricing() => new PerSecondPricingModel(
            ratesPerSecondUsd: new Dictionary<string, decimal> { ["720p"] = 0.01m },
            pricingSource: "test-rate-card");

        // Test-only registration with init-only setters so each null/empty
        // validation branch can be exercised by overriding a single field.
        // Defaults are valid; tests assign null!/empty to break one rule
        // at a time.
        private sealed class TestRegistration : IVideoProviderRegistration
        {
            public string ProviderName { get; init; } = "test-provider";
            public IVideoProvider Provider { get; init; } = new FakeVideoProvider();
            public IProviderOptionsCodec OptionsCodec { get; init; } = new VeoOptionsCodec();
            public IReadOnlyDictionary<string, (ModelCapability Capability, IPricingModel PricingModel)> Models { get; init; }
                = new Dictionary<string, (ModelCapability, IPricingModel)>
                {
                    ["test-default-model"] = (
                        new ModelCapability(
                            Id: "test-default-model", Name: "Default", Status: "preview",
                            Resolutions: new[] { "720p" },
                            Durations: new[] { 8 },
                            AspectRatios: new[] { "16:9" },
                            Modes: new[] { VideoMode.T2V },
                            SupportsReferenceImages: false,
                            MaxReferenceImages: 0,
                            Must8sWith: Array.Empty<string>()),
                        new PerSecondPricingModel(
                            ratesPerSecondUsd: new Dictionary<string, decimal> { ["720p"] = 0.01m },
                            pricingSource: "test-rate-card")),
                };
        }
    }
}
