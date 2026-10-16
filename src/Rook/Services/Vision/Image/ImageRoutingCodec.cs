using System;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Vision.Image
{
    /// <summary>Closed, safe attribution. No upstream strings are admitted into a receipt.</summary>
    public static class ImageRoutingCodec
    {
        public static string? FalModel(string model) => model switch
        {
            "gemini-3.1-flash-image-preview" => "fal-ai/nano-banana-2",
            "gemini-3-pro-image-preview" => "fal-ai/nano-banana-pro",
            _ => null
        };
        public static bool IsFalModel(string model) =>
            model == "fal-ai/nano-banana-2" || model == "fal-ai/nano-banana-pro";
        public static bool IsAffected(string provider, string model) =>
            provider == "gemini" && FalModel(model) != null || provider == "fal" && IsFalModel(model);

        public static JsonObject ToJson(ImageRoutingContext? context, ImageFalDispatchState? falDispatchState = null)
        {
            var obj = new JsonObject();
            if (context?.Route is { } r)
                obj["image_route"] = new JsonObject
                {
                    ["requested_provider"] = r.RequestedProvider, ["requested_model"] = r.RequestedModel,
                    ["effective_provider"] = r.EffectiveProvider, ["effective_model"] = r.EffectiveModel,
                    ["provider_endpoint"] = r.ProviderEndpoint,
                    ["fallback_reason"] = r.FallbackReason switch
                    {
                        ImageFallbackReason.GeminiKeyMissing => "gemini_key_missing",
                        ImageFallbackReason.GeminiKeyRejected => "gemini_key_rejected",
                        _ => throw new ArgumentException("Unknown fallback reason.")
                    },
                    ["phase"] = r.Phase.ToString().ToLowerInvariant(),
                    ["generation_dispatch_attempted"] = r.GenerationDispatchAttempted
                };
            if (context?.CredentialFailure is { } c)
                obj["credential_failure"] = new JsonObject
                { ["provider"] = c.Provider, ["kind"] = c.Kind.ToString().ToLowerInvariant() };
            if (falDispatchState is { } state)
                obj["fal_dispatch_state"] = state switch
                {
                    ImageFalDispatchState.NotStarted => "not_started",
                    ImageFalDispatchState.IntentRecorded => "intent_recorded",
                    ImageFalDispatchState.Attempted => "attempted",
                    _ => throw new ArgumentException("Unknown dispatch state.")
                };
            return obj;
        }

        public static bool TryRead(JsonObject source, string provider, string model,
            out ImageRoutingContext? context, out ImageFalDispatchState? falDispatchState, out string? field)
        {
            context = null; falDispatchState = null; field = null;
            ImageRouteReceipt? route = null;
            ImageCredentialFailure? credential = null;
            if (source["image_route"] is { } routeNode)
            {
                field = "image_route";
                if (routeNode is not JsonObject r || !Keys(r, "requested_provider", "requested_model",
                    "effective_provider", "effective_model", "provider_endpoint", "fallback_reason", "phase",
                    "generation_dispatch_attempted")) return false;
                var requested = Str(r, "requested_model");
                var effective = requested == null ? null : FalModel(requested);
                var endpoint = Str(r, "provider_endpoint");
                if (Str(r, "requested_provider") != "gemini" || effective == null ||
                    Str(r, "effective_provider") != "fal" || Str(r, "effective_model") != effective ||
                    provider != "fal" || model != effective || (endpoint != effective && endpoint != effective + "/edit") ||
                    !EnumText(Str(r, "fallback_reason"), out ImageFallbackReason reason) ||
                    !EnumText(Str(r, "phase"), out ImageExecutionPhase phase) ||
                    r["generation_dispatch_attempted"] is not JsonValue send || !send.TryGetValue<bool>(out var attempted))
                    return false;
                route = new("gemini", requested!, "fal", effective, endpoint!, reason, phase, attempted);
            }
            if (source["credential_failure"] is { } credentialNode)
            {
                field = "credential_failure";
                if (credentialNode is not JsonObject c || !Keys(c, "provider", "kind") ||
                    Str(c, "provider") != provider || !IsAffected(provider, model) ||
                    !EnumText(Str(c, "kind"), out ImageCredentialFailureKind kind)) return false;
                credential = new(provider, kind);
            }
            if (source["fal_dispatch_state"] is { } stateNode)
            {
                field = "fal_dispatch_state";
                if (stateNode is not JsonValue v || !v.TryGetValue<string>(out var text) || !IsAffected(provider, model))
                    return false;
                falDispatchState = text switch
                {
                    "not_started" => ImageFalDispatchState.NotStarted,
                    "intent_recorded" => ImageFalDispatchState.IntentRecorded,
                    "attempted" => ImageFalDispatchState.Attempted, _ => null
                };
                if (falDispatchState == null ||
                    route != null && (falDispatchState == ImageFalDispatchState.Attempted && !route.GenerationDispatchAttempted ||
                    falDispatchState == ImageFalDispatchState.NotStarted && route.GenerationDispatchAttempted)) return false;
            }
            if (route != null || credential != null) context = new(route, credential);
            field = null; return true;
        }

        private static bool Keys(JsonObject obj, params string[] keys) =>
            obj.Count == keys.Length && obj.All(p => keys.Contains(p.Key));
        private static string? Str(JsonObject obj, string key) =>
            obj[key] is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;
        private static bool EnumText<T>(string? value, out T result) where T : struct, Enum
        {
            foreach (T item in Enum.GetValues(typeof(T)))
            {
                var name = item switch
                {
                    ImageFallbackReason.GeminiKeyMissing => "gemini_key_missing",
                    ImageFallbackReason.GeminiKeyRejected => "gemini_key_rejected",
                    _ => item.ToString().ToLowerInvariant()
                };
                if (value == name) { result = item; return true; }
            }
            result = default; return false;
        }
    }
}
