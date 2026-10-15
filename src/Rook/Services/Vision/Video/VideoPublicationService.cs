using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Artifacts;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video
{
    internal sealed class VideoPublicationService
    {
        private readonly ArtifactStore _store;
        private readonly VideoArtifactMaterializer _materializer;
        private readonly Func<Guid, string, JsonNode, Artifact> _setFlag;
        public VideoPublicationService(ArtifactStore store, VideoArtifactMaterializer materializer, Func<Guid, string, JsonNode, Artifact>? setFlag = null) { _store = store; _materializer = materializer; _setFlag = setFlag ?? store.SetFlag; }
        public async Task<Artifact> PrepareAsync(Guid jobId, ResultArtifact result, VideoExecutionSnapshot execution, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            if (result.Role != "video" || result.Body is RemoteArtifactBody remote && !SafeVideoUrl(remote.Url)) throw new InvalidOperationException("Video result URL or role is invalid.");
            var materialized = await _materializer.MaterializeAsync(result, ct).ConfigureAwait(false);
            if (!materialized.Success || materialized.MimeType != "video/mp4" || materialized.Bytes is not { Length: >= 12 } bytes || bytes[4] != 'f' || bytes[5] != 't' || bytes[6] != 'y' || bytes[7] != 'p') throw new InvalidOperationException("Provider result is not a bounded MP4 video.");
            var data = execution.Data;
            var inputs = data["prepared_media"] as JsonArray ?? data["accepted_quote"]?["media"] as JsonArray ?? new JsonArray();
            var parents = inputs.Select(n => Guid.TryParse(n?["artifact_id"]?.GetValue<string>(), out var id) ? id : Guid.Empty).Where(id => id != Guid.Empty).Distinct().ToArray();
            var metadata = new Dictionary<string, JsonNode?> { ["video_job_id"] = JsonValue.Create(jobId.ToString("D")), ["inputs"] = inputs.DeepClone(), ["requested_provider"] = data["requested_provider"]?.DeepClone(), ["requested_model"] = data["requested_model"]?.DeepClone(), ["effective_provider"] = data["effective_provider"]?.DeepClone(), ["effective_model"] = data["effective_model"]?.DeepClone(), ["provider_endpoint"] = data["effective_binding"]?.DeepClone(), ["profile_revision"] = data["profile_revision"]?.DeepClone(), ["effective_options"] = data["effective_options"]?.DeepClone(), ["estimated_pricing"] = data["effective_pricing"]?.DeepClone(), ["video_route"] = data["route_receipt"]?.DeepClone(), ["prompt"] = data["accepted_quote"]?["request"]?["prompt"]?.DeepClone() };
            var artifact = await Task.Run(() => { ct.ThrowIfCancellationRequested(); return _store.Create("generated_video", new[] { new BlobInput("video", bytes, "mp4") }, parents, metadata, new Dictionary<string, JsonNode?> { ["video_publication"] = JsonValue.Create("provisional") }); }).ConfigureAwait(false);
            if (ct.IsCancellationRequested) { _store.Delete(artifact.Id); ct.ThrowIfCancellationRequested(); }
            return artifact;
        }
        private static bool SafeVideoUrl(Uri url) => url.Scheme == "https" && url.IsDefaultPort && url.UserInfo.Length == 0 && !url.IsLoopback && (url.Host == "fal.media" || url.Host.EndsWith(".fal.media", StringComparison.OrdinalIgnoreCase) || url.Host == "generativelanguage.googleapis.com" || url.Host.EndsWith(".googlevideo.com", StringComparison.OrdinalIgnoreCase));
        public static bool IsAffectedArtifact(Artifact artifact) => artifact.Metadata.ContainsKey("video_job_id") || artifact.Flags.ContainsKey("video_publication");
        private static bool Owns(Artifact artifact, VideoJobRecord? durable) => durable != null && artifact.Metadata.TryGetValue("video_job_id", out var owner) && owner is JsonValue value && value.TryGetValue<string>(out var id) && Guid.TryParse(id, out var parsed) && durable.JobId == parsed;
        public bool IsVisible(Artifact artifact, VideoJobRecord? durable) => !IsAffectedArtifact(artifact) || Owns(artifact, durable) && durable!.State == VideoJobState.Complete && durable.ResultArtifactId == artifact.Id && VideoExecutionSnapshot.Read(durable).Error is null;
        internal static bool MarkerPending(Artifact artifact) => !artifact.Flags.TryGetValue("video_publication", out var marker) || marker is not JsonValue value || !value.TryGetValue<string>(out var text) || text != "complete";
        public GenerationError? FinalizeMarker(Artifact artifact)
        {
            try { _setFlag(artifact.Id, "video_publication", JsonValue.Create("complete")!); return null; }
            catch { return Warning("Completed video retained; its publication marker needs repair.", "artifact_marker_pending"); }
        }
        public void RemoveOwnedProvisional(Artifact artifact, VideoJobRecord durable)
        {
            if (!Owns(artifact, durable) || durable.State == VideoJobState.Complete && durable.ResultArtifactId == artifact.Id || !MarkerPending(artifact)) return;
            _store.Delete(artifact.Id);
        }
        public GenerationError? RepairFromLedger(Artifact artifact, VideoJobRecord? durable)
        {
            if (!IsAffectedArtifact(artifact)) return null;
            if (!Owns(artifact, durable)) return Warning("Provisional video hidden because ownership cannot be confirmed.", "artifact_ownership_unknown");
            if (IsVisible(artifact, durable)) return MarkerPending(artifact) ? FinalizeMarker(artifact) : null;
            if (durable!.State is VideoJobState.Interrupted or VideoJobState.Cancelled or VideoJobState.Error) RemoveOwnedProvisional(artifact, durable);
            return null;
        }
        private static GenerationError Warning(string message, string code) => new(GenerationErrorCode.DependencyUnavailable, message, false, null, code);
    }
}
