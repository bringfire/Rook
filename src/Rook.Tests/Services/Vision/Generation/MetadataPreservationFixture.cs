using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Xunit;

namespace Rook.Tests.Services.Vision.Generation
{
    /// <summary>
    /// Provider-native fields round-trip through the
    /// <see cref="ResultArtifact.ProviderMetadata"/> /
    /// <see cref="ProviderResultEnvelope.EnvelopeMetadata"/>
    /// <see cref="JsonNode"/> bags without lossy serialization. The bags
    /// preserve nested objects, arrays, and primitive variants so audit /
    /// replay can reconstruct the provider's response exactly.
    /// </summary>
    public class MetadataPreservationFixture
    {
        [Fact]
        public void ProviderMetadata_roundtrips_nested_structure()
        {
            // fal sync image's per-image metadata shape
            var falImageMeta = new Dictionary<string, JsonNode>
            {
                ["url"] = "https://v3b.fal.media/files/abc/output.jpg",
                ["content_type"] = "image/jpeg",
                ["width"] = 1024,
                ["height"] = 1024,
                ["has_nsfw_concepts"] = false,
            };

            var artifact = new ResultArtifact(
                Role: "image",
                Body: new InlineArtifactBody(new byte[] { 0xFF }),
                DeclaredMimeType: "image/jpeg",
                ProviderMetadata: falImageMeta);

            // Round-trip through JSON serialization (mirrors what the
            // ledger / artifact metadata do at persistence time).
            var json = JsonSerializer.Serialize(artifact.ProviderMetadata);
            var roundtripped = JsonSerializer.Deserialize<Dictionary<string, JsonNode>>(json)!;

            Assert.Equal("image/jpeg", roundtripped["content_type"]!.GetValue<string>());
            Assert.Equal(1024, roundtripped["width"]!.GetValue<int>());
            Assert.False(roundtripped["has_nsfw_concepts"]!.GetValue<bool>());
        }

        [Fact]
        public void EnvelopeMetadata_preserves_gemini_usageMetadata_shape()
        {
            // Gemini's per-modality token detail: nested array of objects
            var usageMetadata = new JsonObject
            {
                ["promptTokenCount"] = 12,
                ["candidatesTokenCount"] = 1290,
                ["promptTokensDetails"] = new JsonArray(
                    new JsonObject { ["modality"] = "TEXT", ["tokenCount"] = 12 }),
                ["candidatesTokensDetails"] = new JsonArray(
                    new JsonObject { ["modality"] = "IMAGE", ["tokenCount"] = 1290 }),
            };

            var envelopeMeta = new Dictionary<string, JsonNode>
            {
                ["modelVersion"] = "gemini-3.1-flash-image-preview",
                ["usageMetadata"] = usageMetadata,
            };

            var json = JsonSerializer.Serialize(envelopeMeta);
            var roundtripped = JsonSerializer.Deserialize<Dictionary<string, JsonNode>>(json)!;

            var usage = (JsonObject)roundtripped["usageMetadata"]!;
            var details = (JsonArray)usage["promptTokensDetails"]!;
            Assert.Equal("TEXT", details[0]!["modality"]!.GetValue<string>());
            Assert.Equal(12, details[0]!["tokenCount"]!.GetValue<int>());
        }

        [Fact]
        public void GenerationError_ProviderDetail_preserves_fastapi_detail_array()
        {
            // FastAPI-style validation error
            var detail = new JsonArray(
                new JsonObject
                {
                    ["loc"] = new JsonArray("body", "input_image_url"),
                    ["msg"] = "Image must be at least 128x128 pixels",
                    ["type"] = "value_error",
                });

            var providerDetail = new Dictionary<string, JsonNode>
            {
                ["detail"] = detail,
            };

            var error = new GenerationError(
                Code: GenerationErrorCode.InvalidRequest,
                Message: "Image must be at least 128x128 pixels",
                Retryable: false,
                ProviderErrorCode: "value_error",
                ProviderDetail: providerDetail);

            var json = JsonSerializer.Serialize(error.ProviderDetail);
            var roundtripped = JsonSerializer.Deserialize<Dictionary<string, JsonNode>>(json)!;
            var detailArr = (JsonArray)roundtripped["detail"]!;
            Assert.Equal("value_error", detailArr[0]!["type"]!.GetValue<string>());
        }
    }
}
