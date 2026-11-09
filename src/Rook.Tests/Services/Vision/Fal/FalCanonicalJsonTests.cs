using System.Text.Json.Nodes;
using Rook.Services.Vision.Fal.Models;
using Xunit;
namespace Rook.Tests.Services.Vision.Fal
{
    public class FalCanonicalJsonTests
    {
        [Theory]
        [InlineData("{\"b\":2,\"a\":1.0}", "{\"a\":1,\"b\":2}")]
        [InlineData("[-0,1e1,0.1000]", "[0,10,0.1]")]
        public void Canonical_hash_ignores_object_order_and_numeric_spelling(string a, string b) => Assert.Equal(Hash(a), Hash(b));
        [Fact]
        public void Canonical_hash_preserves_array_order_and_key_case()
        {
            Assert.NotEqual(Hash("[1,2]"), Hash("[2,1]"));
            Assert.NotEqual(Hash("{\"a\":1}"), Hash("{\"A\":1}"));
        }
        private static string Hash(string json) => FalCanonicalJson.Hash(JsonNode.Parse(json)!);
    }
}
