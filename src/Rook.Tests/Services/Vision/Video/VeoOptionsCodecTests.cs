using System.Text.Json.Nodes;
using Rook.Services.Vision.Video;
using Xunit;

namespace Rook.Tests.Services.Vision.Video
{
    /// <summary>
    /// Codec contract: serialize/deserialize/validate for
    /// <see cref="VeoOptions"/>. The serialize tests use semantic JSON
    /// assertions (per Codex Finding 6); byte equality of the full ledger
    /// line is asserted separately by the bit-identity fixture test.
    /// </summary>
    public class VeoOptionsCodecTests
    {
        // Cap for codec tests: Veo 3.x lite (matches DefaultT2vRequest).
        private static ModelCapability Cap =>
            VeoCapabilities.Models["veo-3.1-lite-generate-preview"].Capability;

        // ─── Serialize (semantic JSON assertions) ─────────────────────

        [Theory]
        [InlineData(PersonGenerationPolicy.AllowAll, "allow_all")]
        [InlineData(PersonGenerationPolicy.AllowAdult, "allow_adult")]
        [InlineData(PersonGenerationPolicy.DontAllow, "dont_allow")]
        public void Serialize_emits_documented_string_for_each_policy(
            PersonGenerationPolicy policy, string expected)
        {
            var codec = new VeoOptionsCodec();
            var json = codec.Serialize(new VeoOptions(policy));

            Assert.Equal(expected, json["person_generation"]?.GetValue<string>());
            Assert.Single(json);
        }

        [Fact]
        public void Serialize_throws_on_non_VeoOptions()
        {
            // Programming-error path: codec is per-provider; misuse means
            // someone bypassed the registry's pairing. Throw loudly.
            var codec = new VeoOptionsCodec();
            var fake = new SomeOtherProviderOptions();

            Assert.Throws<System.InvalidOperationException>(() =>
                codec.Serialize(fake));
        }

        [Fact]
        public void Serialize_throws_on_null()
        {
            var codec = new VeoOptionsCodec();

            Assert.Throws<System.InvalidOperationException>(() =>
                codec.Serialize(null!));
        }

        // ─── Deserialize round-trip ───────────────────────────────────

        [Theory]
        [InlineData("allow_all", PersonGenerationPolicy.AllowAll)]
        [InlineData("allow_adult", PersonGenerationPolicy.AllowAdult)]
        [InlineData("dont_allow", PersonGenerationPolicy.DontAllow)]
        public void Deserialize_round_trips_each_policy_string(
            string jsonStr, PersonGenerationPolicy expected)
        {
            var codec = new VeoOptionsCodec();
            var json = new JsonObject { ["person_generation"] = jsonStr };

            var result = codec.Deserialize(json);

            Assert.True(result.Success);
            var opts = Assert.IsType<VeoOptions>(result.Options);
            Assert.Equal(expected, opts.PersonGeneration);
        }

        [Fact]
        public void Deserialize_then_serialize_round_trips_to_same_json()
        {
            var codec = new VeoOptionsCodec();
            var original = new JsonObject { ["person_generation"] = "allow_adult" };

            var decoded = codec.Deserialize(original);
            Assert.True(decoded.Success);

            var reSerialized = codec.Serialize(decoded.Options!);

            Assert.Equal("allow_adult", reSerialized["person_generation"]?.GetValue<string>());
        }

        [Fact]
        public void Deserialize_fails_on_missing_person_generation_key()
        {
            var codec = new VeoOptionsCodec();
            var json = new JsonObject();

            var result = codec.Deserialize(json);

            Assert.False(result.Success);
            Assert.Equal("person_generation", result.Field);
        }

        [Fact]
        public void Deserialize_fails_on_unknown_string_value()
        {
            var codec = new VeoOptionsCodec();
            var json = new JsonObject { ["person_generation"] = "future_policy_v2" };

            var result = codec.Deserialize(json);

            Assert.False(result.Success);
            Assert.Equal("person_generation", result.Field);
            Assert.Contains("future_policy_v2", result.Message);
        }

        [Fact]
        public void Deserialize_fails_on_null_json()
        {
            var codec = new VeoOptionsCodec();

            var result = codec.Deserialize(null!);

            Assert.False(result.Success);
            Assert.Null(result.Options);
        }

        [Fact]
        public void Deserialize_fails_on_non_string_person_generation()
        {
            var codec = new VeoOptionsCodec();
            var json = new JsonObject { ["person_generation"] = 42 };

            var result = codec.Deserialize(json);

            Assert.False(result.Success);
            Assert.Equal("person_generation", result.Field);
        }

        // ─── Validate (Veo PersonGeneration matrix) ───────────────────

        [Fact]
        public void Validate_accepts_veo3_t2v_with_AllowAll()
        {
            var codec = new VeoOptionsCodec();
            var req = TestVideoFixtures.DefaultT2vRequest(
                personGeneration: PersonGenerationPolicy.AllowAll);

            var result = codec.Validate(req, req.Options, Cap);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_veo3_t2v_with_AllowAdult()
        {
            var codec = new VeoOptionsCodec();
            var req = TestVideoFixtures.DefaultT2vRequest(
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var result = codec.Validate(req, req.Options, Cap);

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        [Fact]
        public void Validate_rejects_veo3_t2v_with_DontAllow()
        {
            var codec = new VeoOptionsCodec();
            var req = TestVideoFixtures.DefaultT2vRequest(
                personGeneration: PersonGenerationPolicy.DontAllow);

            var result = codec.Validate(req, req.Options, Cap);

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        [Fact]
        public void Validate_rejects_veo3_i2v_with_AllowAll()
        {
            var codec = new VeoOptionsCodec();
            // Use full 3.1 cap so I2V is supported with start frame
            var fullCap = VeoCapabilities.Models["veo-3.1-generate-preview"].Capability;
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                mode: VideoMode.I2V,
                prompt: null,
                startFrame: startFrame,
                personGeneration: PersonGenerationPolicy.AllowAll);

            var result = codec.Validate(req, req.Options, fullCap);

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        [Fact]
        public void Validate_accepts_veo3_i2v_with_AllowAdult()
        {
            var codec = new VeoOptionsCodec();
            var fullCap = VeoCapabilities.Models["veo-3.1-generate-preview"].Capability;
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-3.1-generate-preview",
                mode: VideoMode.I2V,
                prompt: null,
                startFrame: startFrame,
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var result = codec.Validate(req, req.Options, fullCap);

            Assert.True(result.Success);
        }

        [Theory]
        [InlineData(PersonGenerationPolicy.AllowAll)]
        [InlineData(PersonGenerationPolicy.AllowAdult)]
        [InlineData(PersonGenerationPolicy.DontAllow)]
        public void Validate_accepts_veo2_t2v_with_any_policy(
            PersonGenerationPolicy policy)
        {
            var codec = new VeoOptionsCodec();
            var veo2Cap = VeoCapabilities.Models["veo-2.0-generate-001"].Capability;
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-2.0-generate-001",
                resolution: "720p",
                duration: 8,
                personGeneration: policy);

            var result = codec.Validate(req, req.Options, veo2Cap);

            Assert.True(result.Success);
        }

        [Fact]
        public void Validate_rejects_veo2_i2v_with_AllowAll()
        {
            var codec = new VeoOptionsCodec();
            var veo2Cap = VeoCapabilities.Models["veo-2.0-generate-001"].Capability;
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-2.0-generate-001",
                mode: VideoMode.I2V,
                resolution: "720p",
                duration: 8,
                prompt: null,
                startFrame: startFrame,
                personGeneration: PersonGenerationPolicy.AllowAll);

            var result = codec.Validate(req, req.Options, veo2Cap);

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        [Theory]
        [InlineData(PersonGenerationPolicy.AllowAdult)]
        [InlineData(PersonGenerationPolicy.DontAllow)]
        public void Validate_accepts_veo2_i2v_with_AllowAdult_or_DontAllow(
            PersonGenerationPolicy policy)
        {
            var codec = new VeoOptionsCodec();
            var veo2Cap = VeoCapabilities.Models["veo-2.0-generate-001"].Capability;
            var startFrame = VideoMediaRef.ForPath(@"C:\fixtures\start.png");
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: "veo-2.0-generate-001",
                mode: VideoMode.I2V,
                resolution: "720p",
                duration: 8,
                prompt: null,
                startFrame: startFrame,
                personGeneration: policy);

            var result = codec.Validate(req, req.Options, veo2Cap);

            Assert.True(result.Success);
        }

        // ─── Reference frames count as image-based ────────────────────

        [Theory]
        [InlineData("veo-3.1-generate-preview")]
        [InlineData("veo-3.1-fast-generate-preview")]
        public void Validate_rejects_veo3_t2v_with_AllowAll_when_reference_frames_present(
            string modelId)
        {
            var codec = new VeoOptionsCodec();
            var cap = VeoCapabilities.Models[modelId].Capability;
            var refs = new[] { VideoMediaRef.ForPath(@"C:\fixtures\ref.png") };
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: modelId,
                mode: VideoMode.T2V,
                resolution: "1080p",
                duration: 8,
                referenceFrames: refs,
                personGeneration: PersonGenerationPolicy.AllowAll);

            var result = codec.Validate(req, req.Options, cap);

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        [Theory]
        [InlineData("veo-3.1-generate-preview")]
        [InlineData("veo-3.1-fast-generate-preview")]
        public void Validate_accepts_veo3_t2v_with_AllowAdult_when_reference_frames_present(
            string modelId)
        {
            var codec = new VeoOptionsCodec();
            var cap = VeoCapabilities.Models[modelId].Capability;
            var refs = new[] { VideoMediaRef.ForPath(@"C:\fixtures\ref.png") };
            var req = TestVideoFixtures.DefaultT2vRequest(
                model: modelId,
                mode: VideoMode.T2V,
                resolution: "1080p",
                duration: 8,
                referenceFrames: refs,
                personGeneration: PersonGenerationPolicy.AllowAdult);

            var result = codec.Validate(req, req.Options, cap);

            Assert.True(result.Success);
        }

        // ─── Undefined-enum guard ─────────────────────────────────────

        [Fact]
        public void Validate_rejects_undefined_PersonGeneration_value()
        {
            var codec = new VeoOptionsCodec();
            var req = TestVideoFixtures.DefaultT2vRequest() with
            {
                Options = new VeoOptions((PersonGenerationPolicy)999),
            };

            var result = codec.Validate(req, req.Options, Cap);

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
            Assert.Contains("Unknown PersonGeneration", result.Message);
        }

        [Fact]
        public void Validate_rejects_negative_undefined_PersonGeneration()
        {
            var codec = new VeoOptionsCodec();
            var req = TestVideoFixtures.DefaultT2vRequest() with
            {
                Options = new VeoOptions((PersonGenerationPolicy)(-1)),
            };

            var result = codec.Validate(req, req.Options, Cap);

            Assert.False(result.Success);
            Assert.Equal("PersonGeneration", result.Field);
        }

        // ─── Type-mismatch + null guards on Validate ──────────────────

        [Fact]
        public void Validate_rejects_null_options_with_typed_failure()
        {
            var codec = new VeoOptionsCodec();
            var req = TestVideoFixtures.DefaultT2vRequest();

            var result = codec.Validate(req, options: null!, Cap);

            Assert.False(result.Success);
            Assert.Equal("options", result.Field);
        }

        [Fact]
        public void Validate_rejects_non_VeoOptions_with_typed_failure()
        {
            var codec = new VeoOptionsCodec();
            var req = TestVideoFixtures.DefaultT2vRequest();
            var fake = new SomeOtherProviderOptions();

            var result = codec.Validate(req, fake, Cap);

            Assert.False(result.Success);
            Assert.Equal("options", result.Field);
            Assert.Contains(nameof(VeoOptions), result.Message);
        }

        // Test-only ProviderOptions subtype to exercise the codec's type
        // discrimination. Lives here so the production code stays Veo-only.
        private sealed record SomeOtherProviderOptions : ProviderOptions;
    }
}
