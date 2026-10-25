using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Rook.Services.Vision.Fal.Models;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Fal
{
    public static class FalExecutionSnapshotCodec
    {
        // Supplied and effective controls duplicate text; JSON escaping may expand each
        // character sixfold. This is separate from the catalog's one-MiB source-file bound.
        internal const int MaxSnapshotBytes = 16 * 1024 * 1024;
        public static JsonObject Serialize(FalExecutionSnapshot snapshot)
        {
            var binding = snapshot.Binding;
            var envelope = new JsonObject { ["schema_version"] = 1, ["definition_id"] = binding.DefinitionId,
                ["revision"] = binding.Revision, ["model_id"] = binding.ModelId, ["display_name"] = binding.DisplayName,
                ["provider"] = "fal", ["status"] = binding.Status, ["operations"] = new JsonArray(binding.ToJson()) };
            var handle = snapshot.Handle;
            var json = new JsonObject { ["version"] = FalExecutionSnapshot.CurrentVersion, ["binding"] = envelope,
                ["binding_digest"] = FalCanonicalJson.Hash(envelope), ["definition_hash"] = binding.DefinitionHash,
                ["supplied_request"] = snapshot.Request.SuppliedRequestFields, ["supplied_options"] = snapshot.Request.SuppliedOptions,
                ["supplied_operation"] = snapshot.Request.SuppliedInput.OperationId,
                ["effective_request"] = snapshot.Request.EffectiveRequestFields, ["effective_options"] = snapshot.Request.EffectiveOptions,
                ["pricing_selectors"] = snapshot.Request.PricingSelectors,
                ["inactive_fields"] = new JsonArray(snapshot.Request.InactiveFields.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()),
                ["media"] = snapshot.MediaProvenance, ["pricing"] = snapshot.Pricing?.ToJson(), ["dispatch_state"] = snapshot.DispatchState, ["submission_outcome"] = snapshot.SubmissionOutcome,
                ["cancellation"] = snapshot.Cancellation?.ToJson(),
                ["handle"] = handle == null ? null : new JsonObject { ["request_id"] = handle.ProviderJobId, ["status_url"] = handle.StatusUrl!.AbsoluteUri,
                    ["response_url"] = handle.ResponseUrl!.AbsoluteUri, ["cancel_url"] = handle.CancelUrl!.AbsoluteUri, ["cancel_http_method"] = "PUT" } };
            if (Encoding.UTF8.GetByteCount(json.ToJsonString()) > MaxSnapshotBytes) throw new ArgumentException("Configured execution history exceeds the bounded persistence envelope.");
            return json;
        }

        public static FalExecutionSnapshotReadResult Deserialize(JsonObject json)
        {
            try
            {
                if (json["version"]?.GetValue<int>() != FalExecutionSnapshot.CurrentVersion)
                    return new(json, null, "Unsupported configured fal execution snapshot version.");
                var encoded = json.ToJsonString();
                if (Encoding.UTF8.GetByteCount(encoded) > MaxSnapshotBytes) throw new ArgumentException();
                using var bounded = JsonDocument.Parse(encoded, new JsonDocumentOptions { MaxDepth = 32 });
                Closed(json, "version", "binding", "binding_digest", "definition_hash", "supplied_request", "supplied_options", "supplied_operation",
                    "effective_request", "effective_options", "pricing_selectors", "inactive_fields", "media", "pricing", "dispatch_state", "submission_outcome", "handle", "cancellation");
                var envelope = json["binding"]!.AsObject();
                if (FalCanonicalJson.Hash(envelope) != json["binding_digest"]!.GetValue<string>()) throw new ArgumentException();
                var binding = FalCatalogCompiler.RestoreBinding(envelope, json["definition_hash"]!.GetValue<string>());
                new FalAdapterRegistry().Resolve(binding.AdapterId, binding.AdapterVersion);
                var media = json["media"]!.AsArray(); var inputs = new List<FalMediaInput>();
                long total = 0;
                foreach (var node in media)
                {
                    var slot = node!.AsObject(); Closed(slot, "role", "ordinal", "artifact_id", "source_role", "source_kind", "sha256", "mime_type", "byte_length");
                    var digest = slot["sha256"]!.GetValue<string>();
                    if (!Regex.IsMatch(digest, @"\A[0-9a-f]{64}\z")) throw new ArgumentException();
                    var role = slot["role"]!.GetValue<string>(); var length = slot["byte_length"]!.GetValue<long>();
                    var definition = binding.Media.Single(m => m.Role == role);
                    if (length <= 0 || length > Math.Min(definition.MaxBytes ?? 30L * 1024 * 1024, 30L * 1024 * 1024)) throw new ArgumentException();
                    total = checked(total + length); if (total > Video.Framing.VideoPreparationLimits.BundleOriginalBytes) throw new ArgumentException();
                    if (slot["mime_type"]!.GetValue<string>() is not ("image/png" or "image/jpeg" or "image/webp")) throw new ArgumentException();
                    var sourceRole = slot["source_role"]!.GetValue<string>();
                    var kind = slot["source_kind"]!.GetValue<string>();
                    if (kind != "Artifact") throw new ArgumentException();
                    var source = MediaRef.ForArtifact(Guid.Parse(slot["artifact_id"]!.GetValue<string>()), sourceRole);
                    inputs.Add(new FalMediaInput(role, slot["ordinal"]!.GetValue<int>(), source));
                }
                var normalized = new FalModelNormalizer().Normalize(binding, new FalModelInput(json["supplied_request"]!.AsObject(),
                    json["supplied_options"]!.AsObject(), json["supplied_operation"]?.GetValue<string>(), inputs));
                if (!normalized.Success) throw new ArgumentException();
                var request = normalized.Request!;
                Equal(request.EffectiveRequestFields, json["effective_request"]!); Equal(request.EffectiveOptions, json["effective_options"]!);
                Equal(request.PricingSelectors, json["pricing_selectors"]!);
                Equal(new JsonArray(request.InactiveFields.Select(s => (JsonNode?)JsonValue.Create(s)).ToArray()), json["inactive_fields"]!);
                ProviderJobHandle? handle = null;
                if (json["handle"] is JsonObject h)
                {
                    Closed(h, "request_id", "status_url", "response_url", "cancel_url", "cancel_http_method");
                    handle = new ProviderJobHandle(h["request_id"]!.GetValue<string>(), new Uri(h["status_url"]!.GetValue<string>()),
                        new Uri(h["response_url"]!.GetValue<string>()), new Uri(h["cancel_url"]!.GetValue<string>()), h["cancel_http_method"]!.GetValue<string>());
                }
                FalPricingSnapshot? pricing = null;
                if (json["pricing"] is JsonObject p)
                {
                    Closed(p, "unit", "revision", "source", "quantity_min", "quantity_max", "rate_usd", "estimate_min_usd", "estimate_max_usd");
                    pricing = FalPricingSnapshot.FromJson(p);
                }
                FalCancellationSnapshot? cancellation = null;
                if (json["cancellation"] != null)
                {
                    var c = json["cancellation"]!.AsObject();
                    Closed(c, "local_stopped", "remote_disposition", "remote_terminal_state", "automatic");
                    cancellation = FalCancellationSnapshot.FromJson(c);
                }
                return new(json, new FalExecutionSnapshot(request, media, pricing, json["dispatch_state"]!.GetValue<string>(), handle, json["submission_outcome"]?.GetValue<string>(), cancellation), null);
            }
            catch (Exception)
            { return new(json, null, "Corrupt or unsupported configured fal execution binding; remote cleanup is unavailable."); }
        }
        private static void Closed(JsonObject json, params string[] keys)
        { if (json.Any(kv => !keys.Contains(kv.Key, StringComparer.Ordinal))) throw new ArgumentException(); }
        private static void Equal(JsonNode a, JsonNode b)
        { if (FalCanonicalJson.Hash(a) != FalCanonicalJson.Hash(b)) throw new ArgumentException(); }
    }

    /// <summary>Retains unsupported records for history without granting lifecycle authority.</summary>
    public sealed class FalExecutionSnapshotReadResult
    {
        private readonly JsonObject _json;
        public JsonObject Json => (JsonObject)_json.DeepClone();
        public FalExecutionSnapshot? Snapshot { get; }
        public string? Diagnostic { get; }
        public bool CleanupAvailable => Snapshot?.Handle != null;
        internal FalExecutionSnapshotReadResult(JsonObject json, FalExecutionSnapshot? snapshot, string? diagnostic)
        { _json = (JsonObject)json.DeepClone(); Snapshot = snapshot; Diagnostic = diagnostic; }
        public static FalExecutionSnapshotReadResult FromSnapshot(FalExecutionSnapshot snapshot)
            => new(FalExecutionSnapshotCodec.Serialize(snapshot), snapshot, null);
    }
}
