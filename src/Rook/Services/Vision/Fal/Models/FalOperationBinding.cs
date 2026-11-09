using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Fal.Models
{
    public sealed class FalOperationBinding
    {
        private readonly JsonObject _json;
        public string ModelId { get; }
        public string DefinitionId { get; }
        public string Revision { get; }
        public string DefinitionHash { get; }
        public string SourceFile { get; }
        public string DisplayName { get; }
        public string Status { get; }
        public string OperationId { get; }
        public string EndpointId { get; }
        public string? LifecycleRoot { get; }
        public string Invocation { get; }
        public string AdapterId { get; }
        public int AdapterVersion { get; }
        public IReadOnlyList<FalFieldDefinition> Fields { get; }
        public IReadOnlyList<FalMediaDefinition> Media { get; }
        public IReadOnlyList<FalConstraintDefinition> Constraints { get; }
        public IReadOnlyList<FalConstantDefinition> Constants { get; }
        public FalResultDefinition Result { get; }
        public FalPricingDefinition? Pricing { get; }
        public FalEvidenceDefinition Evidence { get; }

        internal FalOperationBinding(FalModelDefinition model, JsonObject json)
        {
            _json = (JsonObject)json.DeepClone();
            ModelId = model.ModelId; DefinitionId = model.DefinitionId; Revision = model.Revision;
            DefinitionHash = model.DefinitionHash; SourceFile = model.SourceFile; DisplayName = model.DisplayName; Status = model.Status;
            OperationId = FalValues.String(json, "operation_id"); EndpointId = FalValues.String(json, "endpoint_id");
            LifecycleRoot = json["lifecycle_root"]?.GetValue<string>(); Invocation = FalValues.String(json, "invocation");
            AdapterId = FalValues.String(json["adapter"]!.AsObject(), "id"); AdapterVersion = (int)FalValues.Decimal(json["adapter"]!.AsObject(), "version")!.Value;
            Fields = FalValues.List(json, "fields", o => new FalFieldDefinition(o));
            Media = FalValues.List(json, "media", o => new FalMediaDefinition(o));
            Constraints = FalValues.List(json, "constraints", o => new FalConstraintDefinition(o));
            Constants = FalValues.List(json, "constants", o => new FalConstantDefinition(o));
            Result = new FalResultDefinition(json["result"]!.AsObject());
            Pricing = json["pricing"] is JsonObject pricing ? new FalPricingDefinition(pricing) : null;
            Evidence = new FalEvidenceDefinition(json["evidence"]!.AsObject());
        }
        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }

    public sealed class FalFieldDefinition
    {
        private readonly JsonObject _json;
        internal FalFieldDefinition(JsonObject json) { _json = (JsonObject)json.DeepClone(); Payload = new FalPayloadMapping(json["payload"]!.AsObject()); }
        public string Key => FalValues.String(_json, "key");
        public string Scope => FalValues.String(_json, "scope");
        public string QualifiedKey => Scope + "." + Key;
        public string Type => FalValues.String(_json, "type");
        public string Label => FalValues.String(_json, "label");
        public string? Description => _json["description"]?.GetValue<string>();
        public bool Required => _json["required"]?.GetValue<bool>() ?? false;
        public bool HasDefault => _json.ContainsKey("default");
        public JsonNode? Default => _json["default"]?.DeepClone();
        public decimal? Min => FalValues.Decimal(_json, "min");
        public decimal? Max => FalValues.Decimal(_json, "max");
        public decimal? Step => FalValues.Decimal(_json, "step");
        public int? MinLength => (int?)FalValues.Decimal(_json, "min_length");
        public int? MaxLength => (int?)FalValues.Decimal(_json, "max_length");
        public IReadOnlyList<string> Values => Array.AsReadOnly((_json["values"]?.AsArray() ?? new JsonArray()).Select(n => n!.GetValue<string>()).ToArray());
        public string UiGroup => _json["ui"]?["group"]?.GetValue<string>() ?? "basic";
        public int UiOrder => _json["ui"] is JsonObject ui ? (int)(FalValues.Decimal(ui, "order") ?? 0) : 0;
        public bool Hidden => _json["ui"]?["hidden"]?.GetValue<bool>() ?? false;
        public FalPayloadMapping Payload { get; }
        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }

    public sealed class FalPayloadMapping
    {
        private readonly JsonObject _json;
        internal FalPayloadMapping(JsonObject json) { _json = (JsonObject)json.DeepClone(); }
        public string Pointer => FalValues.String(_json, "pointer");
        public string Conversion => FalValues.String(_json, "conversion");
        public JsonObject? Lookup => _json["lookup"]?.DeepClone().AsObject();
        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }

    public sealed class FalMediaDefinition
    {
        private readonly JsonObject _json;
        internal FalMediaDefinition(JsonObject json) { _json = (JsonObject)json.DeepClone(); Payload = new FalPayloadMapping(json["payload"]!.AsObject()); }
        public string Role => FalValues.String(_json, "role");
        public int MinCount => (int)FalValues.Decimal(_json, "min_count")!.Value;
        public int MaxCount => (int)FalValues.Decimal(_json, "max_count")!.Value;
        public bool Ordered => _json["ordered"]!.GetValue<bool>();
        public string Preparation => FalValues.String(_json, "preparation");
        public string Transport => FalValues.String(_json, "transport");
        public long? MaxBytes => (long?)FalValues.Decimal(_json, "max_bytes");
        public FalPayloadMapping Payload { get; }
        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }

    public sealed class FalConstraintDefinition
    {
        private readonly JsonObject _json;
        internal FalConstraintDefinition(JsonObject json) { _json = (JsonObject)json.DeepClone(); When = FalValues.List(json, "when", o => new FalConditionDefinition(o)); }
        public string Kind => FalValues.String(_json, "kind");
        public string Field => FalValues.String(_json, "field");
        public IReadOnlyList<FalConditionDefinition> When { get; }
        public JsonArray? Values => _json["values"]?.DeepClone().AsArray();
        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }

    public sealed class FalConditionDefinition
    {
        private readonly JsonObject _json;
        internal FalConditionDefinition(JsonObject json) { _json = (JsonObject)json.DeepClone(); }
        public string? Field => _json["field"]?.GetValue<string>();
        public string? Operator => _json["operator"]?.GetValue<string>();
        public string? Role => _json["role"]?.GetValue<string>();
        public bool? Present => _json["present"]?.GetValue<bool>();
        public JsonNode? Value => _json["value"]?.DeepClone();
        public JsonArray? Values => _json["values"]?.DeepClone().AsArray();
        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }

    public sealed class FalConstantDefinition
    {
        private readonly JsonObject _json;
        internal FalConstantDefinition(JsonObject json) { _json = (JsonObject)json.DeepClone(); }
        public string Pointer => FalValues.String(_json, "pointer");
        public JsonNode Value => _json["value"]!.DeepClone();
    }

    public sealed class FalResultDefinition
    {
        private readonly JsonObject _json;
        internal FalResultDefinition(JsonObject json) { _json = (JsonObject)json.DeepClone(); }
        public string Role => FalValues.String(_json, "role");
        public string MimeFamily => FalValues.String(_json, "mime_family");
        public string UrlPointer => FalValues.String(_json, "url_pointer");
        public string? MimePointer => _json["mime_pointer"]?.GetValue<string>();
        public string? CollectionPointer => _json["collection_pointer"]?.GetValue<string>();
        public int Cardinality => 1;
        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }

    public sealed class FalPricingDefinition
    {
        private readonly JsonObject _json;
        internal FalPricingDefinition(JsonObject json) { _json = (JsonObject)json.DeepClone(); Rates = FalValues.List(json, "rates", o => new FalRateDefinition(o)); }
        public string Strategy => FalValues.String(_json, "strategy");
        public string Unit => FalValues.String(_json, "unit");
        public string Revision => FalValues.String(_json, "revision");
        public string Rounding => FalValues.String(_json, "rounding");
        public string Source => FalValues.String(_json, "source");
        public string ReviewedOn => FalValues.String(_json, "reviewed_on");
        public string? QuantityField => _json["quantity_field"]?.GetValue<string>();
        public IReadOnlyList<FalRateDefinition> Rates { get; }
        public JsonObject ToJson() => (JsonObject)_json.DeepClone();
    }

    public sealed class FalRateDefinition
    {
        private readonly JsonObject _json;
        internal FalRateDefinition(JsonObject json) { _json = (JsonObject)json.DeepClone(); }
        public decimal RateUsd => FalValues.Decimal(_json, "rate_usd")!.Value;
        public JsonObject Selectors => _json["selectors"]!.DeepClone().AsObject();
    }

    public sealed class FalEvidenceDefinition
    {
        private readonly JsonObject _json;
        internal FalEvidenceDefinition(JsonObject json) { _json = (JsonObject)json.DeepClone(); }
        public string Url => FalValues.String(_json, "url");
        public string ReviewedOn => FalValues.String(_json, "reviewed_on");
        public string Qualification => FalValues.String(_json, "qualification");
    }

    internal static class FalValues
    {
        internal static string String(JsonObject json, string key) => json[key]!.GetValue<string>();
        internal static decimal? Decimal(JsonObject json, string key) => json[key] == null ? (decimal?)null : decimal.Parse(json[key]!.ToJsonString(), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture);
        internal static IReadOnlyList<T> List<T>(JsonObject json, string key, Func<JsonObject, T> create)
            => Array.AsReadOnly(json[key]!.AsArray().Select(n => create(n!.AsObject())).ToArray());
    }
}
