using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image;
using Rook.Services.Vision.Image.Fal;
using Rook.Services.Vision.Video;
using Rook.Services.Vision.Video.Fal;

namespace Rook.Services.Vision.Fal.Models
{
    /// <summary>One decimal calculator for discovery, quotes and both job modalities.</summary>
    public sealed class FalDeclarativePricing
    {
        public FalPricingResult Estimate(FalNormalizedRequest request)
        {
            if (request == null) throw new ArgumentNullException(nameof(request));
            var p = request.Binding.Pricing;
            if (request.Binding.Status == "disabled" || p == null) return FalPricingResult.Fail(Unavailable());
            try
            {
                var fields = request.EffectiveRequestFields; var options = request.EffectiveOptions;
                JsonNode? Value(string key) => key.StartsWith("request.", StringComparison.Ordinal) ? fields[key.Substring(8)] :
                    key.StartsWith("options.", StringComparison.Ordinal) ? options[key.Substring(8)] : null;
                var rates = p.Rates.Where(r => r.Selectors.All(s => request.Binding.Fields.Any(f => f.QualifiedKey == s.Key && f.Type is "enum" or "boolean")
                    && Value(s.Key) != null && FalModelNormalizer.SameValue(s.Value, Value(s.Key)))).ToArray();
                if (rates.Length != 1) return FalPricingResult.Fail(Unavailable());
                decimal min = 1, max = 1;
                switch (p.Strategy)
                {
                    case "fixed_per_output": if (p.Unit != "output") return FalPricingResult.Fail(Unavailable()); break;
                    case "per_output_second":
                        if (p.Unit != "second" || p.QuantityField == null || !FalCanonicalJson.TryExactDecimal(Value(p.QuantityField), out min) || min <= 0)
                            return FalPricingResult.Fail(Unavailable());
                        max = min; break;
                    case "per_output_megapixel":
                        if (p.Unit != "megapixel") return FalPricingResult.Fail(Unavailable());
                        var json = p.ToJson();
                        if (json["dimensions"] is JsonObject dimensions)
                        {
                            var size = dimensions["values"]?[Value(dimensions["field"]!.GetValue<string>())?.GetValue<string>() ?? ""];
                            if (size == null) return FalPricingResult.Fail(Unavailable());
                            min = checked(size["width"]!.GetValue<decimal>() * size["height"]!.GetValue<decimal>() / 1000000m); max = min;
                            if (min <= 0) return FalPricingResult.Fail(Unavailable());
                        }
                        else if (FalCanonicalJson.TryExactDecimal(json["max_megapixels"], out max) && max > 0) min = 0;
                        else return FalPricingResult.Fail(Unavailable());
                        break;
                    default: return FalPricingResult.Fail(Unavailable());
                }
                if (p.Rounding == "ceil_unit") { min = decimal.Ceiling(min); max = decimal.Ceiling(max); }
                else if (p.Rounding != "none") return FalPricingResult.Fail(Unavailable());
                var rate = rates[0].RateUsd;
                if (rate < 0) return FalPricingResult.Fail(Unavailable());
                var snapshot = new FalPricingSnapshot(p.Unit, p.Revision, p.Source, min, max, rate, checked(min * rate), checked(max * rate));
                if (rate > 0 && (min > 0 && snapshot.EstimateMinUsd == 0 || max > 0 && snapshot.EstimateMaxUsd == 0))
                    return FalPricingResult.Fail(Unavailable());
                // A quote must have a lossless representable public confirmation ceiling.
                FalQuote.PublicCeiling(snapshot.EstimateMaxUsd);
                return FalPricingResult.Ok(snapshot, rates[0].Selectors, p.ReviewedOn);
            }
            catch (Exception ex) when (ex is OverflowException || ex is InvalidOperationException || ex is ArgumentException || ex is FormatException)
            { return FalPricingResult.Fail(Unavailable()); }
        }

        internal static GenerationError Unavailable() => new(GenerationErrorCode.DependencyUnavailable,
            "Configured fal pricing is unavailable for these effective inputs.", false, "pricing", "pricing_unavailable");

        public IPricingModel<ImageGenerationRequest, ImageCapability> ForImage(FalModelDefinition model, FalAdapterRegistry adapters)
            => new ImageProjection(this, new ConfiguredFalImageOptionsCodec(model, adapters));
        public IPricingModel<VideoGenerationRequest, VideoCapability> ForVideo(FalModelDefinition model, FalAdapterRegistry adapters)
            => new VideoProjection(this, new ConfiguredFalVideoOptionsCodec(model, adapters));
        private PricingResult Project(FalNormalizationResult normalized)
        {
            if (!normalized.Success) return PricingResult.Fail(new GenerationError(GenerationErrorCode.InvalidRequest,
                normalized.Errors[0].Message, false, normalized.Errors[0].Field));
            var priced = Estimate(normalized.Request!);
            if (!priced.Success) return PricingResult.Fail(priced.Error!);
            var p = priced.Pricing!;
            return PricingResult.Ok(new Generation.JobPricing("USD", p.RateUsd, p.Unit, p.QuantityMin == p.QuantityMax ? p.QuantityMax : null,
                p.EstimateMaxUsd, p.Source), new CostEstimate(p.EstimateMinUsd, p.EstimateMaxUsd, p.EstimateMinUsd == p.EstimateMaxUsd, p.Revision));
        }
        private abstract class Projection<T, C> : IPricingModel<T, C> where T : GenerationRequest where C : IModelCapability
        {
            protected readonly FalDeclarativePricing Owner;
            protected Projection(FalDeclarativePricing owner) => Owner = owner;
            public string PricingSource => "configured_fal";
            public PricingMetadataLocation MetadataLocation => PricingMetadataLocation.NotApplicable;
            public abstract PricingResult Estimate(T request, C capability);
            // No qualified invoice/billable-unit evidence strategy in schema v1.
            public Generation.JobPricing? ExtractActualSpend(IReadOnlyDictionary<string, IReadOnlyList<string>> headers, JsonNode? body) => null;
            protected static FalModelInput Input(FalModelOptions o) => new(o.Input.RequestFields, o.Input.Options, o.SelectedOperation, o.Input.Media, o.Input.OutputCount);
        }
        private sealed class ImageProjection : Projection<ImageGenerationRequest, ImageCapability>
        {
            private readonly ConfiguredFalImageOptionsCodec _codec;
            internal ImageProjection(FalDeclarativePricing owner, ConfiguredFalImageOptionsCodec codec) : base(owner) => _codec = codec;
            public override PricingResult Estimate(ImageGenerationRequest request, ImageCapability cap)
            {
                var valid = _codec.Validate(request, request.Options, cap);
                if (!valid.Success) return PricingResult.Fail(new GenerationError(GenerationErrorCode.InvalidRequest, valid.Message!, false, valid.Field));
                return request.Options is FalModelOptions o ? Owner.Project(_codec.Normalize(Input(o))) : PricingResult.Fail(Unavailable());
            }
        }
        private sealed class VideoProjection : Projection<VideoGenerationRequest, VideoCapability>
        {
            private readonly ConfiguredFalVideoOptionsCodec _codec;
            internal VideoProjection(FalDeclarativePricing owner, ConfiguredFalVideoOptionsCodec codec) : base(owner) => _codec = codec;
            public override PricingResult Estimate(VideoGenerationRequest request, VideoCapability cap)
            {
                var valid = _codec.Validate(request, request.Options, cap);
                if (!valid.Success) return PricingResult.Fail(new GenerationError(GenerationErrorCode.InvalidRequest, valid.Message!, false, valid.Field));
                return request.Options is FalModelOptions o ? Owner.Project(_codec.Normalize(Input(o))) : PricingResult.Fail(Unavailable());
            }
        }
    }

    public sealed class FalPricingResult
    {
        private readonly JsonObject? _selectors;
        public bool Success => Pricing != null && Error == null;
        public bool Available => Success;
        public FalPricingSnapshot? Pricing { get; }
        public JsonObject? RateSelectors => (JsonObject?)_selectors?.DeepClone();
        public string? ReviewedOn { get; }
        public GenerationError? Error { get; }
        private FalPricingResult(FalPricingSnapshot? pricing, JsonObject? selectors, string? reviewed, GenerationError? error)
        { Pricing = pricing; _selectors = (JsonObject?)selectors?.DeepClone(); ReviewedOn = reviewed; Error = error; }
        internal static FalPricingResult Ok(FalPricingSnapshot pricing, JsonObject selectors, string reviewed) => new(pricing, selectors, reviewed, null);
        internal static FalPricingResult Fail(GenerationError error) => new(null, null, null, error);
    }
}
