using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

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
        internal FalNormalizedRequest(FalOperationBinding binding, FalModelInput input, JsonObject requestFields, JsonObject options,
            IEnumerable<string> inactive, IEnumerable<FalMediaInstruction> media, JsonObject pricingSelectors)
        {
            Binding = binding; SuppliedInput = input;
            _requestFields = (JsonObject)requestFields.DeepClone(); _options = (JsonObject)options.DeepClone();
            _pricingSelectors = (JsonObject)pricingSelectors.DeepClone();
            InactiveFields = Array.AsReadOnly(inactive.ToArray()); Media = Array.AsReadOnly(media.ToArray());
        }
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
