using System.Text.Json.Nodes;
namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalOperationDescriptor
    {
        private readonly JsonObject _json;
        internal FalOperationDescriptor(JsonObject json) { _json = (JsonObject)json.DeepClone(); }
        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }
}
