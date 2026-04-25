using System;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Video
{
    /// <summary>
    /// Veo-specific codec for <see cref="VeoOptions"/>. Owns:
    /// <list type="bullet">
    ///   <item><description>Validation of Veo's PersonGeneration model-family × image-based matrix
    ///     (lifted from V1b's <c>VideoCapabilities.ValidatePersonGeneration</c>).</description></item>
    ///   <item><description>Serialization to <c>{ "person_generation": "&lt;allow_all|allow_adult|dont_allow&gt;" }</c>
    ///     — byte-identical to V1b's <c>VideoJobRecordFactory.BuildProviderOptions</c> output.</description></item>
    ///   <item><description>Deserialization for replay, diagnostics, and future cache keys.</description></item>
    /// </list>
    ///
    /// <para>Mismatched <see cref="ProviderOptions"/> at <see cref="Validate"/>
    /// surfaces as a typed <see cref="ValidationResult.Fail"/>; the same at
    /// <see cref="Serialize"/> throws because reaching Serialize with a
    /// non-<see cref="VeoOptions"/> means the caller bypassed the registry's
    /// codec-to-options pairing — a programming bug, not a runtime input.</para>
    /// </summary>
    public sealed class VeoOptionsCodec : IProviderOptionsCodec
    {
        public ValidationResult Validate(
            VideoGenerationRequest request,
            ProviderOptions options,
            ModelCapability cap)
        {
            if (request is null)
                return ValidationResult.Fail(nameof(request), "Request is null.");

            if (cap is null)
                return ValidationResult.Fail(nameof(cap), "Capability is null.");

            if (options is null)
                return ValidationResult.Fail(
                    nameof(options),
                    "VeoOptions are required for Veo models.");

            if (options is not VeoOptions veo)
                return ValidationResult.Fail(
                    nameof(options),
                    $"Veo codec requires {nameof(VeoOptions)}; got {options.GetType().Name}.");

            // Fail-closed on undefined enum values. C# enums are
            // coercible — (PersonGenerationPolicy)999 can reach this
            // method via cast or reflection. Reject before applying the
            // model/mode table so the branches below only ever see the
            // three defined values. SA_Banana's string-based validator
            // did the equivalent check before the model/mode rules;
            // preserved here under enum typing.
            if (!Enum.IsDefined(typeof(PersonGenerationPolicy), veo.PersonGeneration))
                return ValidationResult.Fail(
                    nameof(VeoOptions.PersonGeneration),
                    $"Unknown PersonGeneration value: {(int)veo.PersonGeneration}.");

            var refCount = request.ReferenceFrames?.Count ?? 0;
            var msg = ValidatePersonGenerationMatrix(
                request.Model, request.Mode, veo.PersonGeneration, refCount, cap);
            if (msg is not null)
                return ValidationResult.Fail(
                    nameof(VeoOptions.PersonGeneration), msg);

            return ValidationResult.Ok();
        }

        public JsonObject Serialize(ProviderOptions options)
        {
            if (options is not VeoOptions veo)
                throw new InvalidOperationException(
                    $"Veo codec cannot serialize {options?.GetType().Name ?? "null"}; " +
                    $"expected {nameof(VeoOptions)}. Caller bypassed the registry's " +
                    "codec-to-options pairing.");

            var json = new JsonObject();
            json["person_generation"] = MapPersonGenerationToJson(veo.PersonGeneration);
            return json;
        }

        public ProviderOptionsDecodeResult Deserialize(JsonObject json)
        {
            if (json is null)
                return ProviderOptionsDecodeResult.Fail(
                    "options", "Provider options JSON is null.");

            if (!json.TryGetPropertyValue("person_generation", out var pgNode)
                || pgNode is null)
                return ProviderOptionsDecodeResult.Fail(
                    "person_generation", "Required field missing.");

            string? pgStr;
            try { pgStr = pgNode.GetValue<string>(); }
            catch
            {
                return ProviderOptionsDecodeResult.Fail(
                    "person_generation", "Field is not a string.");
            }

            var policy = pgStr switch
            {
                "dont_allow" => PersonGenerationPolicy.DontAllow,
                "allow_adult" => PersonGenerationPolicy.AllowAdult,
                "allow_all" => PersonGenerationPolicy.AllowAll,
                _ => (PersonGenerationPolicy?)null,
            };

            if (policy is null)
                return ProviderOptionsDecodeResult.Fail(
                    "person_generation",
                    $"Unknown person_generation value: '{pgStr}'.");

            return ProviderOptionsDecodeResult.Ok(new VeoOptions(policy.Value));
        }

        // ─── Helpers (lifted from V1b's VideoCapabilities) ────────────

        private static string MapPersonGenerationToJson(PersonGenerationPolicy p) => p switch
        {
            PersonGenerationPolicy.DontAllow => "dont_allow",
            PersonGenerationPolicy.AllowAdult => "allow_adult",
            PersonGenerationPolicy.AllowAll => "allow_all",
            _ => throw new ArgumentOutOfRangeException(
                nameof(p), p, "Unknown PersonGenerationPolicy."),
        };

        // PersonGeneration is a Veo API requirement, not a UI nicety.
        // Per Google's docs, only specific values are allowed per
        // (model-family × image-based?) combination; Veo rejects
        // submissions that violate the table. Reference frames count as
        // image-based for this rule even when Mode == T2V — Google
        // groups reference images with i2v/interp explicitly:
        // https://ai.google.dev/gemini-api/docs/video#veo-api-parameters-and-specifications
        // Regional EU/UK/CH/MENA overrides are looser on the server
        // side and deferred to Veo.
        private static string? ValidatePersonGenerationMatrix(
            string modelId,
            VideoMode mode,
            PersonGenerationPolicy personGen,
            int refCount,
            ModelCapability cap)
        {
            var isVeo2 = modelId.StartsWith(
                "veo-2", StringComparison.OrdinalIgnoreCase);

            // "Image-based" for PersonGeneration purposes includes T2V
            // requests that carry reference frames — Google's docs
            // explicitly group reference images with i2v/interp under the
            // allow_adult rule. SA_Banana's lift missed this; we restore
            // the correct shape here. Earlier reference-image gating in
            // CapabilityValidator already rejects refs on models that
            // don't support them, so refCount > 0 here implies a
            // reference-capable Veo 3.x family member (3.1 / 3.1 Fast).
            var imageBased = mode == VideoMode.I2V
                          || mode == VideoMode.Interp
                          || refCount > 0;

            if (isVeo2)
            {
                // Veo 2: T2V allows all three; image-based modes reject AllowAll.
                if (imageBased && personGen == PersonGenerationPolicy.AllowAll)
                    return $"{cap.Name} requires PersonGeneration=AllowAdult or DontAllow " +
                           "for image-based modes (image-to-video, interpolation).";
                return null;
            }

            // Veo 3.x family: docs list exactly one value per mode shape.
            if (imageBased)
            {
                if (personGen != PersonGenerationPolicy.AllowAdult)
                    return $"{cap.Name} requires PersonGeneration=AllowAdult for " +
                           "image-based modes (image-to-video, interpolation, " +
                           "reference images).";
            }
            else // T2V
            {
                if (personGen != PersonGenerationPolicy.AllowAll)
                    return $"{cap.Name} requires PersonGeneration=AllowAll for text-to-video.";
            }

            return null;
        }
    }
}
