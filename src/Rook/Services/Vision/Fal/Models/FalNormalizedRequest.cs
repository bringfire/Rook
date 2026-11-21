using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Text.Json;

namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalNormalizedRequest
    {
        private readonly JsonObject _requestFields;
        private readonly JsonObject _options;
        private readonly JsonObject _pricingSelectors;
        public FalOperationBinding Binding { get; }
        public FalModelInput SuppliedInput { get; }
        public JsonObject SuppliedRequestFields => SuppliedInput.RequestFields;
        public JsonObject SuppliedOptions => SuppliedInput.Options;
        public JsonObject EffectiveRequestFields => (JsonObject)_requestFields.DeepClone();
        public JsonObject EffectiveOptions => (JsonObject)_options.DeepClone();
        public JsonObject PricingSelectors => (JsonObject)_pricingSelectors.DeepClone();
        public IReadOnlyList<string> InactiveFields { get; }
        public IReadOnlyList<FalMediaInstruction> Media { get; }
        // Conservative UTF-16 character/shape units of the already-owned effective controls.
        // Cached here so execution can admit its serialization envelope before cloning getters.
        // Saturation means a future larger input fails admission rather than wrapping the bound.
        internal long EffectiveInputCharacterUnits { get; }
        internal FalNormalizedRequest(FalOperationBinding binding, FalModelInput input, JsonObject requestFields, JsonObject options,
            IEnumerable<string> inactive, IEnumerable<FalMediaInstruction> media, JsonObject pricingSelectors)
        {
            Binding = binding; SuppliedInput = input;
            _requestFields = (JsonObject)requestFields.DeepClone(); _options = (JsonObject)options.DeepClone();
            _pricingSelectors = (JsonObject)pricingSelectors.DeepClone();
            EffectiveInputCharacterUnits = AddUnits(CharacterUnits(_requestFields), CharacterUnits(_options));
            InactiveFields = Array.AsReadOnly(inactive.ToArray()); Media = Array.AsReadOnly(media.ToArray());
        }
        private static long CharacterUnits(JsonNode? node)
        {
            if (node == null) return 4;
            if (node is JsonObject obj)
            {
                long total = 2;
                foreach (var pair in obj) total = AddUnits(total, AddUnits(pair.Key.Length + 4L, CharacterUnits(pair.Value)));
                return total;
            }
            if (node is JsonArray array)
            {
                long total = 2;
                foreach (var item in array) total = AddUnits(total, AddUnits(1, CharacterUnits(item)));
                return total;
            }
            return node.GetValueKind() == JsonValueKind.String ? node.GetValue<string>().Length + 2L : 64;
        }
        private static long AddUnits(long a, long b) => a > long.MaxValue - b ? long.MaxValue : a + b;
    }
    public sealed class FalMediaInstruction
    {
        public FalMediaDefinition Definition { get; }
        public FalMediaInput Input { get; }
        public string Role => Input.Role;
        public int Ordinal => Input.Ordinal;
        internal FalMediaInstruction(FalMediaDefinition definition, FalMediaInput input) { Definition = definition; Input = input; }
    }
}
