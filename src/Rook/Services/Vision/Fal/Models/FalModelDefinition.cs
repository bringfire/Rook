using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Fal.Models
{
    /// <summary>A validated definition. JSON access always returns a detached copy.</summary>
    public sealed class FalModelDefinition
    {
        private readonly JsonObject _json;
        public string DefinitionId { get; }
        public string Revision { get; }
        public string DefinitionHash { get; }
        public string ModelId { get; }
        public string DisplayName { get; }
        public string Provider => "fal";
        public string Status { get; }
        public string SourceFile { get; }
        public IReadOnlyList<FalOperationBinding> Operations { get; }

        internal FalModelDefinition(JsonObject json, string sourceFile)
        {
            _json = (JsonObject)json.DeepClone();
            DefinitionId = FalValues.String(json, "definition_id");
            Revision = FalValues.String(json, "revision");
            DefinitionHash = FalCanonicalJson.Hash(json);
            ModelId = FalValues.String(json, "model_id");
            DisplayName = FalValues.String(json, "display_name");
            Status = FalValues.String(json, "status");
            SourceFile = sourceFile;
            Operations = System.Array.AsReadOnly(json["operations"]!.AsArray()
                .Select(o => new FalOperationBinding(this, o!.AsObject())).ToArray());
        }

        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }
}
