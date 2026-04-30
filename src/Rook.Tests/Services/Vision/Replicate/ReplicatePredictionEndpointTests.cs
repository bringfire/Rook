using System;
using Rook.Services.Vision.Replicate;
using Xunit;

namespace Rook.Tests.Services.Vision.Replicate
{
    public class ReplicatePredictionEndpointTests
    {
        [Fact]
        public void OfficialModel_builds_relative_create_path_from_safe_owner_and_name()
        {
            var endpoint = ReplicatePredictionEndpoint.OfficialModel(
                "black-forest-labs",
                "flux-schnell");

            Assert.Equal("black-forest-labs", endpoint.Owner);
            Assert.Equal("flux-schnell", endpoint.Name);
            Assert.Equal("black-forest-labs/flux-schnell", endpoint.ModelId);
            Assert.Equal(
                "v1/models/black-forest-labs/flux-schnell/predictions",
                endpoint.CreatePredictionPath);
        }

        [Fact]
        public void OfficialModel_escapes_legal_segment_characters_that_need_escaping()
        {
            var endpoint = ReplicatePredictionEndpoint.OfficialModel(
                "owner name",
                "model name");

            Assert.Equal("owner name", endpoint.Owner);
            Assert.Equal("model name", endpoint.Name);
            Assert.Equal("owner name/model name", endpoint.ModelId);
            Assert.Equal(
                "v1/models/owner%20name/model%20name/predictions",
                endpoint.CreatePredictionPath);
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public void OfficialModel_rejects_empty_owner(string owner)
        {
            Assert.Throws<ArgumentException>(() =>
                ReplicatePredictionEndpoint.OfficialModel(owner, "flux-schnell"));
        }

        [Theory]
        [InlineData("")]
        [InlineData("   ")]
        public void OfficialModel_rejects_empty_name(string name)
        {
            Assert.Throws<ArgumentException>(() =>
                ReplicatePredictionEndpoint.OfficialModel("black-forest-labs", name));
        }

        [Theory]
        [InlineData("owner/name")]
        [InlineData("owner?x=1")]
        [InlineData("owner#frag")]
        public void OfficialModel_rejects_owner_path_query_and_fragment_characters(string owner)
        {
            Assert.Throws<ArgumentException>(() =>
                ReplicatePredictionEndpoint.OfficialModel(owner, "flux-schnell"));
        }

        [Theory]
        [InlineData("model/name")]
        [InlineData("model?x=1")]
        [InlineData("model#frag")]
        public void OfficialModel_rejects_name_path_query_and_fragment_characters(string name)
        {
            Assert.Throws<ArgumentException>(() =>
                ReplicatePredictionEndpoint.OfficialModel("black-forest-labs", name));
        }

        [Fact]
        public void Endpoint_descriptor_does_not_claim_generic_prediction_endpoint_support()
        {
            var endpoint = ReplicatePredictionEndpoint.OfficialModel("owner", "name");

            Assert.Equal("v1/models/owner/name/predictions", endpoint.CreatePredictionPath);
            Assert.NotEqual("v1/predictions", endpoint.CreatePredictionPath);
        }
    }
}
