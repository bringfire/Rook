using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Image.Jobs;
using Rook.Handlers;

namespace Rook.Services.Vision.Image
{
    public static class ImageFailureProjection
    {
        public static Dictionary<string, object?> Build(GenerationError error, string provider, string model,
            ImageRoutingContext? routing, ImageFalDispatchState? falDispatchState = null)
        {
            var safe = ImageJobLedgerRecordFactory.SanitizeError(error)!;
            var data = new Dictionary<string, object?>
            {
                ["code"] = Code(safe.Code), ["message"] = safe.Message,
                ["retryable"] = safe.Retryable, ["field"] = safe.Field,
                ["provider"] = provider, ["model"] = model
            };
            AddRouting(data, provider, model, routing, falDispatchState);
            return data;
        }
        internal static void AddRouting(Dictionary<string, object?> data, string? provider, string? model,
            ImageRoutingContext? routing, ImageFalDispatchState? dispatch)
        {
            if (provider == null || model == null) return;
            data["provider"] = provider; data["model"] = model;
            foreach (var p in ImageRoutingCodec.ToJson(routing, dispatch)) data[p.Key] = p.Value?.DeepClone();
        }
        internal static ApiResponse? FromExecution(GenerationError error, ImageExecutionContext context)
        {
            var s = context.Snapshot();
            var provider = s.Routing?.Route?.EffectiveProvider ?? s.EffectiveModel?.ProviderName;
            var model = s.Routing?.Route?.EffectiveModel ?? s.EffectiveModel?.ModelId;
            if (provider == null || model == null || s.Routing?.Route == null &&
                !(provider == "fal" && ImageRoutingCodec.IsFalModel(model)) &&
                !(error.Code == GenerationErrorCode.Interrupted && ImageRoutingCodec.IsAffected(provider, model))) return null;
            return new ApiResponse { Success = false,
                Data = Build(error, provider, model, s.Routing, s.FalDispatchState),
                HttpStatus = ImageJobOpHandler.MapStatusFromCode(error.Code) };
        }
        internal static ApiResponse Timeout(string message, ImageExecutionContext? context)
        {
            if (context != null)
            {
                context.SetCredentialFailure(null);
                context.SetPhase(ImageExecutionPhase.Interruption);
                var structured = FromExecution(new(GenerationErrorCode.Interrupted, message, false), context);
                if (structured != null) return structured;
            }
            return new ApiResponse { Success = false, Data = message };
        }
        internal static void AddArtifactRouting(IDictionary<string, JsonNode?> metadata, ImageExecutionSnapshot s)
        {
            if (s.Routing?.Route is not { } route) return;
            metadata["provider"] = route.EffectiveProvider;
            metadata["model"] = route.EffectiveModel;
            metadata["requested_provider"] = route.RequestedProvider;
            metadata["requested_model"] = route.RequestedModel;
            metadata["provider_endpoint"] = route.ProviderEndpoint;
            metadata["fallback_reason"] = route.FallbackReason == ImageFallbackReason.GeminiKeyMissing
                ? "gemini_key_missing" : "gemini_key_rejected";
            metadata["image_route"] = ImageRoutingCodec.ToJson(s.Routing)["image_route"]?.DeepClone();
        }
        private static string Code(GenerationErrorCode code) => code switch
        {
            GenerationErrorCode.InvalidRequest => "invalid_request", GenerationErrorCode.UnsupportedMedia => "unsupported_media",
            GenerationErrorCode.DependencyUnavailable => "dependency_unavailable", GenerationErrorCode.ExecutionFailed => "execution_failed",
            GenerationErrorCode.QuotaExceeded => "quota_exceeded", GenerationErrorCode.ContentPolicy => "content_policy",
            _ => code.ToString().ToLowerInvariant()
        };
    }
}
