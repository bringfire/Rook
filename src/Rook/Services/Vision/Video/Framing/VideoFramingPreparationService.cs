using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rook.Services.Vision.Generation;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed class VideoFramingPreparationService
    {
        private readonly IMediaResolver _media;
        private readonly VideoFramingCache _cache;
        private readonly IVideoSourceRenderer _renderer;
        internal VideoPreparationResources Resources { get; }
        internal VideoFramingCache Cache => _cache;
        internal GenerationError? ValidateProfile(VideoRequestIntent intent)
            => intent.Request.SourceFraming != null && _renderer.VerifyProfile() is string failure
                ? VideoSourcePreparationErrors.Create("source_preparation_failed", "source_framing", intent.Request.SourceFraming.Value.Wire(), failure) : null;
        public VideoFramingPreparationService(IMediaResolver media, VideoFramingCache cache, IVideoSourceRenderer? renderer = null, VideoPreparationResources? resources = null)
        { _media = media; _cache = cache; _renderer = renderer ?? new FfmpegVideoSourceRenderer(); Resources = resources ?? VideoPreparationResources.Shared; }
        internal static GenerationError? ValidateUse(VideoGenerationRequest request)
        {
            if (request.SourceFraming == null) return null;
            if (request.SourceFraming is not (SourceFramingMode.Fit or SourceFramingMode.Fill) || !VideoSubmissionCoordinator.IsAffectedModel(request.Model) ||
                request.Mode is not (VideoMode.I2V or VideoMode.Interp) || request.StartFrame == null || (request.ReferenceFrames?.Count ?? 0) != 0 ||
                request.Mode == VideoMode.I2V && request.EndFrame != null || request.Mode == VideoMode.Interp && request.EndFrame == null)
                return new(GenerationErrorCode.InvalidRequest, "Source framing supports Veo 3.1 image-to-video and interpolation with start/end frames.", false, "source_framing");
            return null;
        }
        public async Task<VideoFramingPreviewResult> PreviewAsync(VideoFramingPreviewRequest request, CancellationToken ct)
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct); deadline.CancelAfter(TimeSpan.FromSeconds(15));
            var roles = request.Mode == VideoMode.I2V ? new[] { "start_frame" } : request.Mode == VideoMode.Interp ? new[] { "start_frame", "end_frame" } : Array.Empty<string>();
            if (roles.Length == 0 || !request.Sources.Select(s => s.Role).SequenceEqual(roles)) return new(null, null, Invalid("Supply the required start/end image roles.", "sources"));
            var domain = new VideoGenerationRequest(request.Model, request.Mode, 8, request.Resolution, request.AspectRatio, null,
                request.Sources[0].Ref, request.Sources.Count == 2 ? request.Sources[1].Ref : null, null, null, new VeoOptions(PersonGenerationPolicy.AllowAdult), 1, SourceFramingMode.Fit);
            var error = ValidateUse(domain); if (error != null) return new(null, null, error);
            try
            {
                using var phase = await Resources.AcquireAsync(deadline.Token).ConfigureAwait(false);
                var read = await ReadOriginalsAsync(domain, phase, deadline.Token).ConfigureAwait(false);
                if (read.Snapshot == null) return new(null, null, read.Error);
                using var originals = read.Snapshot;
                var fit = await PrepareAsync(domain, originals, phase, deadline.Token).ConfigureAwait(false);
                using var fitPin = fit.Bundle;
                var fitPreview = Project(fit);
                VideoPreparedBundleResult fill;
                try { fill = await PrepareAsync(domain.With(sourceFraming: SourceFramingMode.Fill), originals, phase, deadline.Token).ConfigureAwait(false); }
                catch (OperationCanceledException) when (!ct.IsCancellationRequested)
                { fill = new(null, VideoSourcePreparationErrors.Busy("source_framing")); }
                using var fillPin = fill.Bundle;
                return new(fitPreview, Project(fill), null);
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested) { return new(null, null, VideoSourcePreparationErrors.Busy("source_framing")); }
            catch (VideoPreparationBusyException) { return new(null, null, VideoSourcePreparationErrors.Busy("source_framing")); }
        }
        public async Task<VideoPreparedBundleResult> PrepareSelectedAsync(VideoRequestIntent intent, VideoPreparationLease lease, CancellationToken ct)
        {
            var error = ValidateUse(intent.Request); if (error != null) return new(null, error);
            var read = await ReadOriginalsAsync(intent.Request, lease, ct).ConfigureAwait(false);
            if (read.Snapshot == null) return new(null, read.Error);
            using var originals = read.Snapshot;
            return await PrepareAsync(intent.Request, originals, lease, ct).ConfigureAwait(false);
        }
        internal async Task<VideoSourceSnapshotResult> ReadOriginalsAsync(VideoGenerationRequest request, VideoPreparationLease phase, CancellationToken ct)
        {
            if (_media is ArtifactOnlyVideoMediaResolver artifacts) return await artifacts.ResolveSnapshotAsync(request, phase, ct).ConfigureAwait(false);
            using var resolved = await _media.ResolveAllAsync(VideoRouteQuoteService.VideoMediaReferences(request), ct).ConfigureAwait(false);
            if (!resolved.Success) return new(null, resolved.Error);
            try { return new(VideoPreparedMediaSnapshot.Capture(request, resolved.Resolved!, phase), null); }
            catch (ArgumentException) { return new(null, VideoSourcePreparationErrors.Create("source_input_too_large", "media")); }
        }
        private async Task<VideoPreparedBundleResult> PrepareAsync(VideoGenerationRequest request, VideoPreparedMediaSnapshot originals, VideoPreparationLease phase, CancellationToken ct)
        {
            if (request.SourceFraming != null && _renderer.VerifyProfile() is string profileFailure)
                return new(null, VideoSourcePreparationErrors.Create("source_preparation_failed", "source_framing", request.SourceFraming.Value.Wire(), profileFailure));
            var identity = new JsonObject { ["originals"] = VideoRouteQuoteService.ProjectMedia(originals), ["model"] = request.Model,
                ["resolution"] = request.Resolution, ["aspect"] = request.AspectRatio, ["mode"] = request.SourceFraming?.Wire(),
                ["profile"] = request.SourceFraming == null ? null : VideoFramingRecipe.ProfileRevision,
                ["renderer"] = request.SourceFraming == null ? null : VideoFramingRendererProfile.Sha256 };
            string key = VideoEstimateFingerprint.Compute(identity);
            var hit = _cache.TryGet(key); if (hit != null) return new(hit, null);
            if (request.SourceFraming == null)
            {
                var legacy = originals.Retain(); return Admit(new(legacy, legacy, null));
            }
            if (request.Model.IndexOf("lite", StringComparison.Ordinal) >= 0 && request.Resolution == "4k") return new(null, Invalid("This model does not support 4k.", "resolution"));
            var prepared = new Dictionary<MediaRef, VideoResolvedSource>(); var descriptions = new Dictionary<MediaRef, JsonObject>();
            bool transferred = false;
            try
            {
                foreach (var slot in originals.Slots)
                {
                    ct.ThrowIfCancellationRequested(); if (prepared.ContainsKey(slot.Ref)) continue;
                    var inspected = VideoStillImageInspector.Inspect(slot.Buffer, slot.Role);
                    if (inspected.Error != null) return new(null, inspected.Error);
                    var info = inspected.Info!;
                    var geometry = VideoFramingGeometry.Create(info, request.Resolution, request.AspectRatio, request.SourceFraming.Value, slot.Role);
                    if (geometry.Error != null) return new(null, geometry.Error);
                    var rendered = await _renderer.RenderAsync(slot.Buffer, info, new(request.SourceFraming.Value, info, geometry.Layout!, VideoFramingRendererProfile.Sha256), phase, ct).ConfigureAwait(false);
                    if (rendered.Source == null) return new(null, rendered.Error! with { Field = slot.Role });
                    using var source = rendered.Source;
                    prepared.Add(slot.Ref, new(source.Bytes.Retain(), source.MimeType));
                    descriptions.Add(slot.Ref, new JsonObject {
                        ["original_sha256"] = slot.Sha256, ["original_byte_length"] = slot.ByteLength, ["original_mime_type"] = info.MimeType,
                        ["original_width"] = info.Width, ["original_height"] = info.Height, ["oriented_width"] = info.OrientedWidth, ["oriented_height"] = info.OrientedHeight,
                        ["prepared_sha256"] = source.Bytes.Sha256, ["prepared_byte_length"] = source.Bytes.Length, ["prepared_mime_type"] = source.MimeType,
                        ["width"] = source.Recipe.Layout.CanvasWidth, ["height"] = source.Recipe.Layout.CanvasHeight, ["upscaled"] = source.Recipe.Layout.Upscaled,
                        ["recipe"] = source.Recipe.Canonical() });
                }
                var slots = new JsonArray(originals.Slots.Select(s => { var obj = (JsonObject)descriptions[s.Ref].DeepClone(); obj["role"] = s.Role; obj["artifact_id"] = s.Ref.ArtifactId?.ToString("D"); obj["source_role"] = s.Ref.Role; return (JsonNode?)obj; }).ToArray());
                var evidence = new JsonObject { ["version"] = 1, ["mode"] = request.SourceFraming.Value.Wire(), ["profile"] = VideoFramingRecipe.ProfileRevision, ["renderer_sha256"] = VideoFramingRendererProfile.Sha256, ["slots"] = slots };
                var snapshot = VideoPreparedMediaSnapshot.FromOwned(originals.Slots.Select(s => (s.Role, s.Ref)), prepared);
                transferred = true; return Admit(new(originals.Retain(), snapshot, evidence));
            }
            finally { if (!transferred) foreach (var value in prepared.Values) value.Buffer.Dispose(); }
            VideoPreparedBundleResult Admit(VideoPreparedBundle bundle)
            { var pin = _cache.Admit(key, bundle); return pin == null ? new(null, VideoSourcePreparationErrors.Busy("source_framing")) : new(pin, null); }
        }
        private static VideoFramingPreviewVariant Project(VideoPreparedBundleResult result)
        {
            if (result.Bundle == null) return new(Array.Empty<VideoFramingPreviewSlot>(), result.Error);
            var bundle = result.Bundle; var details = bundle.SourcePreparation!["slots"]!.AsArray();
            return new(bundle.Prepared.Slots.Select((slot, i) => {
                var d = details[i]!; return new VideoFramingPreviewSlot(slot.Role, bundle.PreviewId(slot.Role), slot.Sha256,
                    d["width"]!.GetValue<int>(), d["height"]!.GetValue<int>(), d["oriented_width"]!.GetValue<int>(), d["oriented_height"]!.GetValue<int>(), d["upscaled"]!.GetValue<bool>());
            }).ToArray(), null);
        }
        private static GenerationError Invalid(string message, string field) => new(GenerationErrorCode.InvalidRequest, message, false, field);
    }
}
