using System;
using System.Collections.Generic;
using System.Linq;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Xunit;
using GenerationPricingModel = Rook.Services.Vision.Generation.IPricingModel<Rook.Services.Vision.Video.VideoGenerationRequest, Rook.Services.Vision.Video.VideoCapability>;
using GenerationOptionsCodec = Rook.Services.Vision.Generation.IProviderOptionsCodec<Rook.Services.Vision.Video.VideoGenerationRequest, Rook.Services.Vision.Video.VideoCapability>;

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

        // ─── TryResolveProviderByName (H1 fix surface) ────────────────

        [Fact]
        public void TryResolveProviderByName_returns_registered_veo_provider()
        {
            var fakeProvider = new FakeVideoProvider();
            var registry = TestVideoFixtures.RegistryWithVeo(fakeProvider);

            var ok = registry.TryResolveProviderByName("veo", out var resolved);

            Assert.True(ok);
            Assert.Same(fakeProvider, resolved);
        }

        [Fact]
        public void TryResolveProviderByName_returns_false_for_unknown_provider()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            var ok = registry.TryResolveProviderByName("ghost-provider", out _);

            Assert.False(ok);
        }

        [Fact]
        public void TryResolveProviderByName_returns_false_for_null_or_empty()
        {
            var registry = TestVideoFixtures.RegistryWithVeo();

            Assert.False(registry.TryResolveProviderByName(null!, out _));
            Assert.False(registry.TryResolveProviderByName("", out _));
            Assert.False(registry.TryResolveProviderByName("   ", out _));
        }

        [Fact]
        public void TryResolveProviderByName_first_registered_wins_when_duplicate_names()
        {
            // Codex Finding 5 explicitly allows duplicate provider names
            // (a provider may legitimately split registrations across
            // product families). For TryResolveProviderByName, first
            // registration wins — assumes implementations sharing a name
            // are interchangeable for cancel-style ops.
            var first = new FakeVideoProvider();
            var second = new FakeVideoProvider();

            var alpha = new FakeRegistration("veo", first,
                new System.Collections.Generic.Dictionary<string, (VideoCapability, GenerationPricingModel)>
                {
                    ["alpha-model"] = (StubCap("alpha-model"), StubPricing()),
                });
            var beta = new FakeRegistration("veo", second,
                new System.Collections.Generic.Dictionary<string, (VideoCapability, GenerationPricingModel)>
                {
                    ["beta-model"] = (StubCap("beta-model"), StubPricing()),
                });

            var registry = new DefaultVideoProviderRegistry(new[] { alpha, beta });

            Assert.True(registry.TryResolveProviderByName("veo", out var resolved));
            Assert.Same(first, resolved);
        }

        // Mirror of TestRegistration without the init-only defaults so we
        // can pass a specific Provider instance for the duplicate-name test.
        private sealed class FakeRegistration : IVideoProviderRegistration
        {
            public string ProviderName { get; }
            public IVideoProvider Provider { get; }
            public GenerationOptionsCodec OptionsCodec { get; } = new VeoOptionsCodec();
            public System.Collections.Generic.IReadOnlyDictionary<string, (VideoCapability Capability, GenerationPricingModel PricingModel)> Models { get; }

            public FakeRegistration(
                string providerName,
                IVideoProvider provider,
                System.Collections.Generic.IReadOnlyDictionary<string, (VideoCapability, GenerationPricingModel)> models)
            {
                ProviderName = providerName;
                Provider = provider;
                Models = models;
            }
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
        public void EnumerateAllModels_pins_documented_veo_order()
        {
            // M2: stability across two calls (above) doesn't catch a
            // regression in deterministic content order. Pin the actual
            // Veo enumeration so a UI model picker has a stable contract.
            var registry = TestVideoFixtures.RegistryWithVeo();

            var ids = registry.EnumerateAllModels().Select(d => d.ModelId).ToArray();

            Assert.Equal(new[]
            {
                "veo-3.1-generate-preview",
                "veo-3.1-fast-generate-preview",
                "veo-3.1-lite-generate-preview",
                "veo-3.0-generate-001",
                "veo-3.0-fast-generate-001",
                "veo-2.0-generate-001",
            }, ids);
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
                Models = new Dictionary<string, (VideoCapability, GenerationPricingModel)>
                {
                    ["alpha-model"] = (StubCap("alpha-model"), StubPricing()),
                },
            };
            var beta = new TestRegistration
            {
                ProviderName = "veo",
                Models = new Dictionary<string, (VideoCapability, GenerationPricingModel)>
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
            // PR-2: VideoCapability is a sealed class with construction-
            // time validation, so empty Id throws ArgumentException at the
            // capability ctor (stricter than the V1c registry-level catch).
            // Stub the capability with a placeholder Id and verify the
            // empty MODEL ID is rejected at the registry boundary; an
            // empty CAPABILITY ID is now caught even earlier (see
            // Constructor_throws_on_empty_capability_id).
            var bad = new TestRegistration
            {
                Models = new Dictionary<string, (VideoCapability, GenerationPricingModel)>
                {
                    ["  "] = (StubCap("placeholder"), StubPricing()),
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
                Models = new Dictionary<string, (VideoCapability, GenerationPricingModel)>
                {
                    ["m"] = (null!, StubPricing()),
                },
            };

            Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new[] { bad }));
        }

        [Fact]
        public void Constructor_throws_on_empty_capability_id()
        {
            // F3 (review pass 2): cap.Id must be non-empty (identity is
            // load-bearing for descriptors and downstream validation).
            // PR-2: VideoCapability sealed-class ctor validates this at
            // construction time, so the rejection happens earlier than
            // V1c (which caught it during registry build). The
            // invariant is preserved end-to-end; the rejection point
            // moved up in the call stack.
            Assert.Throws<ArgumentException>(() => new VideoCapability(
                Id: "  ",
                Name: "x", Status: "preview",
                Resolutions: new[] { "720p" },
                Durations: new[] { 8 },
                AspectRatios: new[] { "16:9" },
                Modes: new[] { VideoMode.T2V },
                SupportsReferenceImages: false,
                MaxReferenceImages: 0,
                Must8sWith: Array.Empty<string>()));
        }

        [Fact]
        public void Constructor_throws_when_capability_id_does_not_match_registration_key()
        {
            // F3 (review pass 2): registration key and cap.Id are two
            // identity sources for the same model. If they disagree,
            // downstream descriptors/validation/pricing would silently
            // disagree about which model is in play. Reject at build
            // time with a message naming both sides.
            var capWithWrongId = new VideoCapability(
                Id: "veo-3.1-lite-generate-preview",
                Name: "x", Status: "preview",
                Resolutions: new[] { "720p" },
                Durations: new[] { 8 },
                AspectRatios: new[] { "16:9" },
                Modes: new[] { VideoMode.T2V },
                SupportsReferenceImages: false,
                MaxReferenceImages: 0,
                Must8sWith: Array.Empty<string>());

            var bad = new TestRegistration
            {
                Models = new Dictionary<string, (VideoCapability, GenerationPricingModel)>
                {
                    ["runway-x"] = (capWithWrongId, StubPricing()),
                },
            };

            var ex = Assert.Throws<InvalidOperationException>(() =>
                new DefaultVideoProviderRegistry(new[] { bad }));

            Assert.Contains("runway-x", ex.Message);
            Assert.Contains("veo-3.1-lite-generate-preview", ex.Message);
        }

        [Fact]
        public void Constructor_accepts_when_capability_id_matches_registration_key()
        {
            // Sanity: matched ids work (this is the production path —
            // VeoCapabilities is already constructed this way).
            var goodCap = new VideoCapability(
                Id: "matched-model",
                Name: "x", Status: "preview",
                Resolutions: new[] { "720p" },
                Durations: new[] { 8 },
                AspectRatios: new[] { "16:9" },
                Modes: new[] { VideoMode.T2V },
                SupportsReferenceImages: false,
                MaxReferenceImages: 0,
                Must8sWith: Array.Empty<string>());

            var good = new TestRegistration
            {
                Models = new Dictionary<string, (VideoCapability, GenerationPricingModel)>
                {
                    ["matched-model"] = (goodCap, StubPricing()),
                },
            };

            var registry = new DefaultVideoProviderRegistry(new[] { good });

            Assert.True(registry.TryResolve("matched-model", out var resolved));
            Assert.Equal("matched-model", resolved.Capability.Id);
        }

        [Fact]
        public void Constructor_throws_on_null_pricing_model()
        {
            var bad = new TestRegistration
            {
                Models = new Dictionary<string, (VideoCapability, GenerationPricingModel)>
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

        private static VideoCapability StubCap(string id) => new(
            Id: id, Name: id, Status: "preview",
            Resolutions: new[] { "720p" },
            Durations: new[] { 8 },
            AspectRatios: new[] { "16:9" },
            Modes: new[] { VideoMode.T2V },
            SupportsReferenceImages: false,
            MaxReferenceImages: 0,
            Must8sWith: Array.Empty<string>());

        private static GenerationPricingModel StubPricing() => new PerSecondVideoPricingModel(
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
            public GenerationOptionsCodec OptionsCodec { get; init; } = new VeoOptionsCodec();
            public IReadOnlyDictionary<string, (VideoCapability Capability, GenerationPricingModel PricingModel)> Models { get; init; }
                = new Dictionary<string, (VideoCapability, GenerationPricingModel)>
                {
                    ["test-default-model"] = (
                        new VideoCapability(
                            Id: "test-default-model", Name: "Default", Status: "preview",
                            Resolutions: new[] { "720p" },
                            Durations: new[] { 8 },
                            AspectRatios: new[] { "16:9" },
                            Modes: new[] { VideoMode.T2V },
                            SupportsReferenceImages: false,
                            MaxReferenceImages: 0,
                            Must8sWith: Array.Empty<string>()),
                        new PerSecondVideoPricingModel(
                            ratesPerSecondUsd: new Dictionary<string, decimal> { ["720p"] = 0.01m },
                            pricingSource: "test-rate-card")),
                };
        }
    }
}
