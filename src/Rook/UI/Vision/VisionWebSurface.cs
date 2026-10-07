using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Rhino;
using Rook.Artifacts;
using Rook.Handlers;
using Rook.Services.Vision;
using Rook.Services.Vision.Generation;
using Rook.Services.Vision.Video;
using Rook.UI.Web;

namespace Rook.UI.Vision
{
    /// <summary>
    /// Pattern A web surface for the Vision tab. The Vision UI is fully
    /// in-process: every call that would otherwise have crossed an HTTP
    /// boundary is routed through the JS ↔ C# bridge shim registered here
    /// under the single method <c>vision</c>, discriminated by the inner
    /// <c>op</c> field.
    ///
    /// Routing splits into two handler tracks. Image ops go to
    /// <see cref="VisionHandler"/>; V2 video ops go to
    /// <see cref="VideoOpHandler"/>. The handler choice is made per-op
    /// via <see cref="VideoOps"/> membership; the dispatcher kind
    /// (Async / Ui / OffUi) comes from <see cref="OpRoutes"/>.
    ///
    /// <list type="bullet">
    ///   <item><c>generate</c>, <c>enhance_prompt</c>, <c>test_api_key</c>
    ///         → <see cref="VisionHandler.DispatchAsync"/> (network,
    ///         cancellable).</item>
    ///   <item><c>capture_depth</c>, <c>capture_viewport</c>,
    ///         <c>preview_viewport</c>, <c>list_views</c>
    ///         → <see cref="VisionHandler.Dispatch"/> on the Rhino UI
    ///         thread (viewport state / modal dialog).</item>
    ///   <item><c>list_artifacts</c>, <c>get_artifact</c>,
    ///         <c>approve_artifact</c>, <c>delete_artifact</c>,
    ///         <c>consume_approved</c>, <c>set_api_key</c>,
    ///         <c>get_settings_overview</c>,
    ///         <c>open_artifacts_folder</c>,
    ///         <c>reveal_artifact_file</c>
    ///         → <see cref="VisionHandler.DispatchOffUi"/> (disk or secret
    ///         store; threadpool-offloaded so a large artifact store
    ///         scan doesn't stall Rhino).</item>
    ///   <item><c>submit_video_job</c>, <c>cancel_video_job</c>
    ///         → <see cref="VideoOpHandler.DispatchAsync"/> (network
    ///         via the Veo provider; cancellable). Submit kicks off a
    ///         background job and returns Queued; cancel makes a
    ///         provider HTTP call.</item>
    ///   <item><c>get_video_job</c>, <c>get_video_job_result</c>,
    ///         <c>estimate_video_job</c>
    ///         → <see cref="VideoOpHandler.DispatchOffUi"/> (ledger
    ///         reads + pure-CPU pricing; threadpool-offloaded).</item>
    /// </list>
    ///
    /// The native HTTP trampoline at
    /// <c>NativeGhBridgeRegistrar.HandleVisionDispatch</c> mirrors this
    /// fork so the tab and GH NLE consumers go through the same
    /// <see cref="VideoJobManager"/> instance via
    /// <see cref="RookSubsystemRoot.Video"/>.
    ///
    /// Unknown ops return a structured failure envelope
    /// (<c>{success:false, data:"Unknown vision op..."}</c>) instead of
    /// raising — so a bad op name at the JS layer surfaces as a
    /// user-addressable error rather than a generic "handler failed"
    /// from <see cref="BridgeDispatcher"/>'s exception path. This is the
    /// explicit allowlist the scope pass called for — no default-to-offUi
    /// fallback that would mis-route a future UI-thread op.
    ///
    /// CSP: overrides the substrate default to <c>connect-src 'none'</c>
    /// — the Vision tab must not talk to <c>127.0.0.1:*</c> because there
    /// is no chat-server involvement, and a slip into network traffic
    /// would violate the Pattern A boundary. Gallery thumbnails load via
    /// the <c>/blob/{artifact_id}/{role}</c> virtual resource on the
    /// same <c>https://app.rook.invalid</c> origin, covered by
    /// <c>img-src 'self'</c>.
    ///
    /// Virtual resources: <c>/blob/{artifact_id}/{role}</c> streams blob
    /// bytes from <see cref="ArtifactStore.GetBlobAbsolutePath"/>. Path
    /// validation (canonicalization, directory-escape rejection, role
    /// pattern, file existence) is inherited from the store — the
    /// subclass adds the URI shape check and the segment-count guard.
    /// </summary>
    public sealed class VisionWebSurface : RookWebSurface
    {
        // ─── Resource contract ────────────────────────────────────────

        protected override string ResourceRoot => "Rook.UI.Vision.Resources";
        protected override string EntryPage => "index.html";

        /// <summary>
        /// Self-contained fallback shown when WebView2 is unavailable
        /// (net48 runtime or initialization failure). Fully inline — no
        /// relative URLs, no external fonts.
        /// </summary>
        protected override string MinimalFallbackHtml => @"<!DOCTYPE html>
<html><head><meta charset='UTF-8'>
<style>
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #1e1e1e; color: #e0e0e0; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
.msg { text-align: center; opacity: 0.7; max-width: 320px; padding: 20px; }
h1 { margin: 0 0 12px; font-weight: 500; font-size: 18px; }
p { margin: 8px 0; line-height: 1.4; }
</style></head><body>
<div class='msg'>
  <h1>Vision</h1>
  <p>WebView unavailable.</p>
  <p>Restart Rhino to retry, or check that Microsoft Edge WebView2 Runtime is installed.</p>
</div>
</body></html>";

        // ─── CSP override ─────────────────────────────────────────────

        /// <summary>
        /// Content-Security-Policy for the Vision tab (v1). The value is
        /// regression-pinned in <c>Rook.Tests/UI/Web/VisionWebSurfaceTests.cs</c>
        /// — silent drift would reintroduce network affordances the
        /// Pattern A boundary exists to prevent.
        /// </summary>
        internal const string VisionContentSecurityPolicy =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "style-src 'self' 'unsafe-inline'; " +
            "font-src 'self'; " +
            "img-src 'self' data:; " +
            // PR-V3: <video src="/blob/{id}/video"> for generated video
            // playback. media-src defaults to default-src ('none') under
            // CSP3, so omitting this directive blocks <video>/<audio>
            // even though img-src 'self' covers <img>. Same-origin only;
            // does not relax network egress (connect-src 'none' stands).
            "media-src 'self'; " +
            "connect-src 'none';";

        protected override string ContentSecurityPolicy => VisionContentSecurityPolicy;

        // ─── Op-routing table ─────────────────────────────────────────

        internal enum VisionOpRoute
        {
            Async,   // DispatchAsync (network-bound)
            Ui,      // Dispatch (Rhino UI thread)
            OffUi,   // DispatchOffUi (threadpool — disk / secret store)
        }

        /// <summary>
        /// Explicit allowlist of ops the JS bridge is willing to relay
        /// to <see cref="VisionHandler"/>, paired with the dispatcher
        /// each one must land in. There is NO default route — an op not
        /// in this dictionary returns a structured "Unknown vision op"
        /// failure. Routing decisions live here; schema validation is
        /// the dispatcher's responsibility on the other side.
        /// </summary>
        internal static readonly IReadOnlyDictionary<string, VisionOpRoute> OpRoutes =
            new Dictionary<string, VisionOpRoute>(StringComparer.Ordinal)
            {
                ["generate"] = VisionOpRoute.Async,
                ["enhance_prompt"] = VisionOpRoute.Async,
                ["test_api_key"] = VisionOpRoute.Async,
                ["test_provider_secret"] = VisionOpRoute.Async,

                ["capture_depth"] = VisionOpRoute.Ui,
                ["capture_viewport"] = VisionOpRoute.Ui,
                ["preview_viewport"] = VisionOpRoute.Ui,
                ["list_views"] = VisionOpRoute.Ui,

                // Presentation reconciler (spec 2026-06-10): substrate-
                // wide diagnostics dump + operator-forced repair. UI-
                // thread — touches the WebView2 controller and schedules
                // repairs via the Eto UI scheduler.
                ["get_presentation_diagnostics"] = VisionOpRoute.Ui,
                ["repair_presentation"] = VisionOpRoute.Ui,

                ["list_artifacts"] = VisionOpRoute.OffUi,
                ["get_artifact"] = VisionOpRoute.OffUi,
                ["approve_artifact"] = VisionOpRoute.OffUi,
                ["delete_artifact"] = VisionOpRoute.OffUi,
                ["consume_approved"] = VisionOpRoute.OffUi,
                ["set_api_key"] = VisionOpRoute.OffUi,
                ["set_provider_secret"] = VisionOpRoute.OffUi,
                ["clear_provider_secret"] = VisionOpRoute.OffUi,
                ["get_settings_overview"] = VisionOpRoute.OffUi,
                ["list_image_models"] = VisionOpRoute.OffUi,
                ["open_artifacts_folder"] = VisionOpRoute.OffUi,
                ["reveal_artifact_file"] = VisionOpRoute.OffUi,

                // V2 video ops — routed to VideoOpHandler instead of
                // VisionHandler. The dispatcher kind (Async / OffUi)
                // matches the native trampoline's mapping; the handler
                // fork happens at the bridge level via VideoOps lookup.
                [VideoOpHandler.OpSubmit] = VisionOpRoute.Async,
                [VideoOpHandler.OpCancel] = VisionOpRoute.Async,
                [VideoOpHandler.OpStatus] = VisionOpRoute.OffUi,
                [VideoOpHandler.OpResult] = VisionOpRoute.OffUi,
                [VideoOpHandler.OpEstimate] = VisionOpRoute.OffUi,

                // PR-V3 (bridge-only, NOT in native trampoline allowlist):
                // ledger reads + registry enumeration. Kept off the native
                // HTTP surface in V3; PR-V4 lands native + MCP-tool parity.
                [VideoOpHandler.OpListJobs] = VisionOpRoute.OffUi,
                [VideoOpHandler.OpListModels] = VisionOpRoute.OffUi,

                // Hidden image job ops — bridge-only; native HTTP and MCP
                // exposure are intentionally out of scope for Task 7.
                [ImageJobOpHandler.OpStart] = VisionOpRoute.Async,
                [ImageJobOpHandler.OpCancel] = VisionOpRoute.Async,
                [ImageJobOpHandler.OpStatus] = VisionOpRoute.OffUi,
                [ImageJobOpHandler.OpResult] = VisionOpRoute.OffUi,
                [ImageJobOpHandler.OpList] = VisionOpRoute.OffUi,

                // Media gallery import ops — bridge-only v1. The picker
                // is UI-thread work; job status/list reads are off-UI.
                [MediaImportOpHandler.OpStart] = VisionOpRoute.Ui,
                [MediaImportOpHandler.OpStatus] = VisionOpRoute.OffUi,
                [MediaImportOpHandler.OpList] = VisionOpRoute.OffUi,
            };

        /// <summary>
        /// Long-form video op names handled by <see cref="VideoOpHandler"/>
        /// rather than <see cref="VisionHandler"/>. Lookup is O(1) so the
        /// per-call routing fork is cheap. Source of truth is
        /// <see cref="VideoOpHandler"/>'s op constants — if those drift,
        /// this set drifts in lockstep.
        /// </summary>
        internal static readonly HashSet<string> VideoOps =
            new(StringComparer.Ordinal)
            {
                VideoOpHandler.OpSubmit,
                VideoOpHandler.OpCancel,
                VideoOpHandler.OpStatus,
                VideoOpHandler.OpResult,
                VideoOpHandler.OpEstimate,
                VideoOpHandler.OpListJobs,
                VideoOpHandler.OpListModels,
            };

        private static readonly HashSet<string> ImageJobOps =
            new(StringComparer.Ordinal)
            {
                ImageJobOpHandler.OpStart,
                ImageJobOpHandler.OpCancel,
                ImageJobOpHandler.OpStatus,
                ImageJobOpHandler.OpResult,
                ImageJobOpHandler.OpList,
            };

        internal static readonly HashSet<string> MediaImportOps =
            new(StringComparer.Ordinal)
            {
                MediaImportOpHandler.OpStart,
                MediaImportOpHandler.OpStatus,
                MediaImportOpHandler.OpList,
            };

        /// <summary>
        /// Reconstruction bridge ops that are network-bound and must run
        /// under <see cref="AsyncOpTimeout"/> via
        /// <see cref="DispatchWithTimeoutAsync"/> — parity with the Vision
        /// and Video async paths. Off-UI ops (models / list_jobs /
        /// job_result) are disk/catalog reads and are dispatched directly.
        /// </summary>
        internal static readonly HashSet<string> ReconstructionAsyncOps =
            new(StringComparer.Ordinal)
            {
                "submit_job",
                "job_status",
                "cancel_job",
                "import_package",
                "remove_background",
            };

        // ─── Timeouts ─────────────────────────────────────────────────

        /// <summary>
        /// Upper bound for every async bridge op
        /// (<c>generate</c>, <c>enhance_prompt</c>, <c>test_api_key</c>).
        /// Matches the native <c>vision_dispatch</c> trampoline's 180 s
        /// ceiling in <c>NativeGhBridgeRegistrar.HandleVisionDispatch</c>
        /// so both entry points behave symmetrically. The probe op
        /// (<c>test_api_key</c>) typically completes in under 2 s; 180 s
        /// is only the hard cap.
        /// </summary>
        internal static readonly TimeSpan AsyncOpTimeout = TimeSpan.FromSeconds(180);

        // ─── State ────────────────────────────────────────────────────

        private readonly VisionHandler _handler;
        private readonly VideoOpHandler? _videoHandler;
        private readonly ImageJobOpHandler? _imageJobHandler;
        private readonly MediaImportOpHandler? _mediaImportHandler;
        private readonly ArtifactStore _artifactStore;

        /// <summary>
        /// Production constructor. Wires every long-lived dependency
        /// against the shared <see cref="RookSubsystemRoot"/> singletons
        /// so the tab, the native HTTP trampoline, and any future
        /// consumer (GH NLE) observe the SAME instances:
        /// <list type="bullet">
        ///   <item><see cref="ArtifactStore"/> — single in-memory cache
        ///         and write coordinator (writes from one entry point
        ///         are visible to the other without disk re-reads).</item>
        ///   <item><see cref="VisionSecretStore"/> — single API-key
        ///         source. A user setting the key in the tab's settings
        ///         pane is visible to the native HTTP path on its next
        ///         provider call.</item>
        ///   <item><see cref="VideoJobManager"/> via
        ///         <see cref="RookSubsystemRoot.Video"/> — single
        ///         running-jobs dict, single ledger writer.</item>
        /// </list>
        /// Codex review of step 6 caught this: the prior ctor built
        /// <see cref="VisionHandler"/> with its parameterless default,
        /// which spawned fresh <see cref="ArtifactStore"/> +
        /// <see cref="VisionSecretStore"/> instances pointing at the
        /// same disk root but holding independent in-memory state. The
        /// explicit internal ctor below threads the shared singletons
        /// through correctly.
        /// </summary>
        public VisionWebSurface() : this(
            BuildSharedVisionHandler(),
            BuildSharedVideoHandler(),
            BuildSharedImageJobHandler(),
            BuildSharedMediaImportHandler(),
            RookSubsystemRoot.Instance.SharedArtifactStore)
        { }

        /// <summary>
        /// Legacy two-arg test constructor. Test rigs that don't
        /// exercise V2 video ops can keep this signature; the bridge
        /// handler null-guards video routing so a test that
        /// accidentally sends a video op gets a structured failure
        /// instead of an NRE. New test rigs should prefer the three-
        /// arg ctor with an explicit (possibly stub) video handler.
        /// </summary>
        internal VisionWebSurface(VisionHandler handler, ArtifactStore artifactStore)
            : this(
                handler,
                videoHandler: null,
                imageJobHandler: null,
                mediaImportHandler: null,
                artifactStore) { }

        internal VisionWebSurface(
            VisionHandler handler,
            VideoOpHandler? videoHandler,
            ImageJobOpHandler? imageJobHandler,
            MediaImportOpHandler? mediaImportHandler,
            ArtifactStore artifactStore)
        {
            _handler = handler ?? throw new ArgumentNullException(nameof(handler));
            _videoHandler = videoHandler;
            _imageJobHandler = imageJobHandler;
            _mediaImportHandler = mediaImportHandler;
            _artifactStore = artifactStore ?? throw new ArgumentNullException(nameof(artifactStore));

            // Register the single op-discriminated bridge method. Must
            // happen in the constructor so the handler is attached
            // before ConfigureVirtualHost runs and the bridge-unavailable
            // lifecycle fires.
            RegisterBridgeHandler("vision", HandleVisionBridgeCallAsync);
            RegisterBridgeHandler("reconstruction", HandleReconstructionBridgeCallAsync);
        }

        internal VisionWebSurface(
            VisionHandler handler,
            VideoOpHandler? videoHandler,
            ImageJobOpHandler? imageJobHandler,
            ArtifactStore artifactStore)
            : this(
                handler,
                videoHandler,
                imageJobHandler,
                mediaImportHandler: null,
                artifactStore)
        { }

        private static VideoOpHandler BuildSharedVideoHandler()
        {
            var bundle = RookSubsystemRoot.Instance.Video;
            return new VideoOpHandler(bundle.Manager, bundle.Registry, bundle.Estimator);
        }

        private static ImageJobOpHandler BuildSharedImageJobHandler()
        {
            var handler = BuildSharedVisionHandler();
            var bundle = RookSubsystemRoot.Instance.ImageJobs;
            return new ImageJobOpHandler(bundle.Manager, handler);
        }

        private static MediaImportOpHandler BuildSharedMediaImportHandler() =>
            new MediaImportOpHandler(
                RookSubsystemRoot.Instance.MediaImports,
                new EtoMediaImportPicker());

        private static VisionHandler BuildSharedVisionHandler()
        {
            // Threads the shared ArtifactStore + VisionSecretStore from
            // RookSubsystemRoot through VisionHandler's explicit internal
            // ctor. PromptEnhancer/ViewportHandler are stateless leaves;
            // fresh instances are correct here.
            return new VisionHandler(
                artifactStore: RookSubsystemRoot.Instance.SharedArtifactStore,
                generationSecrets: RookSubsystemRoot.Instance.SharedGenerationSecretStore,
                enhancer: new PromptEnhancer(),
                viewportHandler: new ViewportHandler(),
                imageProviderRegistry: RookSubsystemRoot.Instance.ImageJobs.Registry);
        }

        // ─── Bridge handler ───────────────────────────────────────────

        /// <summary>
        /// Top-level relay for <c>window.rookBridge.invoke("vision", {op, ...})</c>.
        /// Routes by <see cref="OpRoutes"/> to the correct
        /// <see cref="VisionHandler"/> dispatcher, then wraps the
        /// <see cref="ApiResponse"/> as a <c>{success, data}</c> JsonNode.
        /// </summary>
        private async Task<JsonNode?> HandleVisionBridgeCallAsync(JsonNode? argsNode)
        {
            string? body = argsNode?.ToJsonString();
            string? op = PeekOp(body);

            if (string.IsNullOrEmpty(op))
            {
                return BuildFailure("Vision request missing required 'op' discriminator.");
            }
            if (!OpRoutes.TryGetValue(op!, out var route))
            {
                return BuildFailure($"Unknown vision op '{op}'.");
            }

            // V2: video ops (submit/cancel/status/result/estimate) route
            // to VideoOpHandler instead of VisionHandler. The dispatcher
            // kind (Async / OffUi) still comes from OpRoutes; the
            // handler choice is the per-op fork. UI-only ops never
            // belong to VideoOps (video has no Rhino-touching ops in V2).
            var isImageJobOp = ImageJobOps.Contains(op!);
            var isVideoOp = VideoOps.Contains(op!);
            var isMediaImportOp = MediaImportOps.Contains(op!);

            if (isVideoOp && _videoHandler is null)
            {
                // Defensive: legacy 2-arg test rigs that don't wire a
                // video handler. Production paths always use the
                // parameterless ctor or pass an explicit handler.
                return BuildFailure(
                    "Video subsystem unavailable in this surface (no VideoOpHandler injected).");
            }
            if (isImageJobOp && _imageJobHandler is null)
            {
                return BuildFailure("Image job subsystem unavailable in this surface.");
            }
            if (isMediaImportOp && _mediaImportHandler is null)
            {
                return BuildFailure("Media import subsystem unavailable in this surface.");
            }

            ApiResponse response;
            try
            {
                switch (route)
                {
                    case VisionOpRoute.Async:
                        response = isImageJobOp
                            ? await DispatchImageJobAsyncWithTimeoutAsync(op!, body).ConfigureAwait(false)
                            : isVideoOp
                                ? await DispatchVideoAsyncWithTimeoutAsync(op!, body).ConfigureAwait(false)
                            : await DispatchAsyncWithTimeoutAsync(op!, body).ConfigureAwait(false);
                        break;
                    case VisionOpRoute.Ui:
                        // No video op routes through Ui — capture_depth
                        // and friends are image-only. Defensive: if a
                        // future video op needs UI thread (it shouldn't
                        // — video doesn't touch Rhino state), this
                        // branch would land at _handler.Dispatch and
                        // fail with "unknown op." That's the right
                        // failure — a misconfigured route should NOT
                        // silently land in the wrong handler.
                        response = await InvokeOnUiAsync(
                            () => isMediaImportOp
                                ? _mediaImportHandler!.DispatchUi(body)
                                : _handler.Dispatch(body)).ConfigureAwait(false);
                        break;
                    case VisionOpRoute.OffUi:
                        // Off-UI ops are disk-only (artifact store) or
                        // secret-store reads, plus video ledger reads
                        // and estimator pricing. VisionHandler.DispatchOffUi
                        // and VideoOpHandler.DispatchOffUi are both sync
                        // with no CancellationToken; the native
                        // trampoline wraps these in a 30 s wait at the
                        // transport layer. JS bridge relies on bounded
                        // disk I/O (v1 artifact store has no indexing).
                        response = isImageJobOp
                            ? await Task.Run(
                                () => _imageJobHandler!.DispatchOffUi(body)).ConfigureAwait(false)
                            : isMediaImportOp
                                ? await Task.Run(
                                    () => _mediaImportHandler!.DispatchOffUi(body)).ConfigureAwait(false)
                            : isVideoOp
                                ? await Task.Run(
                                    () => _videoHandler!.DispatchOffUi(body)).ConfigureAwait(false)
                            : await Task.Run(
                                () => _handler.DispatchOffUi(body)).ConfigureAwait(false);
                        break;
                    default:
                        return BuildFailure($"Unhandled route for op '{op}'.");
                }
            }
            catch (Exception ex)
            {
                Log($"Rook: vision bridge op '{op}' threw: {ex.GetType().Name}: {ex.Message}");
                // Surface a generic failure — never leak exception text to JS.
                return BuildFailure($"Vision op '{op}' failed.");
            }

            return ApiResponseToJsonNode(response);
        }

        /// <summary>
        /// Thin UI bridge for <c>window.rookBridge.invoke("reconstruction", {op, ...})</c>.
        /// Keeps the v1 Vision affordance labeled and routed through the
        /// dedicated Reconstruction domain rather than tunneling through Vision.
        /// </summary>
        private async Task<JsonNode?> HandleReconstructionBridgeCallAsync(JsonNode? argsNode)
        {
            string? body = argsNode?.ToJsonString();
            string? op = PeekOp(body);

            if (string.IsNullOrEmpty(op))
            {
                return BuildFailure("Reconstruction request missing required 'op' discriminator.");
            }

            ApiResponse response;
            try
            {
                if (ReconstructionAsyncOps.Contains(op))
                {
                    response = await DispatchWithTimeoutAsync(
                        op,
                        AsyncOpTimeout,
                        token => RookSubsystemRoot.Instance.Reconstruction.DispatchAsync(body, token),
                        domainLabel: "Reconstruction")
                        .ConfigureAwait(false);
                }
                else if (op is "models" or "list_jobs" or "job_result")
                {
                    response = await Task.Run(
                        () => RookSubsystemRoot.Instance.Reconstruction.DispatchOffUi(body))
                        .ConfigureAwait(false);
                }
                else
                {
                    response = new ApiResponse
                    {
                        Success = false,
                        Data = $"Unknown reconstruction op '{op}'.",
                        HttpStatus = 400,
                    };
                }
            }
            catch (Exception ex)
            {
                Log($"Rook: reconstruction bridge op '{op}' threw: {ex.GetType().Name}: {ex.Message}");
                return BuildFailure($"Reconstruction op '{op}' failed.");
            }

            return ApiResponseToJsonNode(response);
        }

        /// <summary>
        /// Video-side analog of <see cref="DispatchAsyncWithTimeoutAsync"/>
        /// — same <see cref="AsyncOpTimeout"/>, same timeout-rewrite
        /// rules (see <see cref="DispatchWithTimeoutAsync"/>), but
        /// dispatches through <see cref="VideoOpHandler.DispatchAsync"/>.
        /// </summary>
        private Task<ApiResponse> DispatchVideoAsyncWithTimeoutAsync(string op, string? body)
            => DispatchWithTimeoutAsync(
                op,
                AsyncOpTimeout,
                token => _videoHandler!.DispatchAsync(body, token));

        private Task<ApiResponse> DispatchImageJobAsyncWithTimeoutAsync(string op, string? body)
            => DispatchWithTimeoutAsync(
                op,
                AsyncOpTimeout,
                token => _imageJobHandler!.DispatchAsync(body, token));

        /// <summary>
        /// Instance entry point: dispatch an async op through
        /// <see cref="VisionHandler.DispatchAsync"/> under the standard
        /// <see cref="AsyncOpTimeout"/>. Thin wrapper around the pure
        /// <see cref="DispatchWithTimeoutAsync"/> helper, which isolates
        /// the cancellation-to-timeout rewrite so it can be exercised
        /// in unit tests without a real <see cref="VisionHandler"/>.
        /// </summary>
        private Task<ApiResponse> DispatchAsyncWithTimeoutAsync(string op, string? body)
            => DispatchWithTimeoutAsync(
                op,
                AsyncOpTimeout,
                token => _handler.DispatchAsync(body, token));

        /// <summary>
        /// Pure timeout-wrapper: run <paramref name="dispatch"/> under a
        /// per-call <see cref="CancellationTokenSource"/> bounded by
        /// <paramref name="timeout"/>, and return an
        /// <see cref="ApiResponse"/>. Two cancellation paths are
        /// handled:
        /// <list type="bullet">
        ///   <item><b>Observed</b>: the dispatcher honors the token and
        ///         throws <see cref="OperationCanceledException"/> when
        ///         the CTS fires. We catch it and return a fresh
        ///         failure envelope whose <c>Data</c> reads
        ///         <c>"Vision op '{op}' timed out after {N}s."</c>.</item>
        ///   <item><b>Swallowed</b>: the dispatcher's own generic
        ///         exception catch converts the cancellation into a
        ///         <c>Success=false</c> envelope. We detect this via
        ///         <see cref="CancellationTokenSource.IsCancellationRequested"/>
        ///         and rewrite <c>Data</c> in place so the caller sees
        ///         the actual cause instead of "See Rhino command line
        ///         for details."</item>
        /// </list>
        /// Happy path passes through unchanged. Exceptions that are not
        /// cancellations (or fire before the CTS) propagate to the
        /// outer bridge-handler catch.
        /// </summary>
        internal static async Task<ApiResponse> DispatchWithTimeoutAsync(
            string op,
            TimeSpan timeout,
            Func<CancellationToken, Task<ApiResponse>> dispatch,
            string domainLabel = "Vision")
        {
            using var cts = new CancellationTokenSource(timeout);
            ApiResponse response;
            try
            {
                response = await dispatch(cts.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cts.IsCancellationRequested)
            {
                return new ApiResponse
                {
                    Success = false,
                    Data = $"{domainLabel} op '{op}' timed out after {timeout.TotalSeconds:F0}s.",
                };
            }

            if (!response.Success && cts.IsCancellationRequested)
            {
                response.Data = $"{domainLabel} op '{op}' timed out after {timeout.TotalSeconds:F0}s.";
            }
            return response;
        }

        /// <summary>
        /// Run <paramref name="func"/> on Rhino's UI thread via
        /// <c>Eto.Forms.Application.Instance.AsyncInvoke</c> and return a
        /// Task that completes with its result. Bridge callbacks enter on
        /// the WebView2 message thread — which is typically the UI thread
        /// already, but we marshal unconditionally so a prior <c>await</c>
        /// that resumed on a threadpool context cannot starve us of UI
        /// affinity before touching Rhino state.
        /// </summary>
        private static Task<ApiResponse> InvokeOnUiAsync(Func<ApiResponse> func)
        {
            var tcs = new TaskCompletionSource<ApiResponse>();
            try
            {
                Eto.Forms.Application.Instance.AsyncInvoke(() =>
                {
                    try { tcs.SetResult(func()); }
                    catch (Exception ex) { tcs.SetException(ex); }
                });
            }
            catch (Exception ex)
            {
                // Eto application may be unavailable in test contexts —
                // surface synchronously so the caller's catch runs.
                tcs.SetException(ex);
            }
            return tcs.Task;
        }

        internal static string? PeekOp(string? requestJson)
        {
            if (string.IsNullOrEmpty(requestJson)) return null;
            try
            {
                using var doc = JsonDocument.Parse(requestJson!);
                if (doc.RootElement.ValueKind != JsonValueKind.Object) return null;
                if (!doc.RootElement.TryGetProperty("op", out var opEl)) return null;
                if (opEl.ValueKind != JsonValueKind.String) return null;
                return opEl.GetString();
            }
            catch (JsonException)
            {
                return null;
            }
        }

        internal static JsonNode ApiResponseToJsonNode(ApiResponse response)
        {
            var obj = new JsonObject { ["success"] = response.Success };

            // ApiResponse.Data is `object?`. Round-trip through JsonSerializer
            // to land a faithful JsonNode — Dictionary<string, object?>,
            // strings, ints, and nested objects all serialize correctly.
            if (response.Data is null)
            {
                obj["data"] = null;
            }
            else
            {
                try
                {
                    var raw = JsonSerializer.Serialize(response.Data);
                    obj["data"] = JsonNode.Parse(raw);
                }
                catch (Exception ex)
                {
                    obj["success"] = false;
                    obj["data"] = $"Vision response serialization failed: {ex.Message}";
                }
            }
            return obj;
        }

        internal static JsonNode BuildFailure(string message)
            => new JsonObject { ["success"] = false, ["data"] = message };

        // ─── Virtual resources: /blob/* and /viewport-preview/* ───────

        /// <summary>
        /// Test-only accessor for <see cref="TryResolveVirtualResource"/>.
        /// The real hook is <c>protected virtual</c> on the substrate;
        /// reaching it from xUnit requires an internal bridge plus
        /// <c>InternalsVisibleTo("Rook.Tests")</c> (already on Rook.csproj).
        /// Not part of any production contract.
        /// </summary>
        internal VirtualResource? ResolveVirtualResourceForTest(Uri uri)
            => TryResolveVirtualResource(uri);

        protected override VirtualResource? TryResolveVirtualResource(Uri uri)
        {
            if (IsViewportPreviewPath(uri))
            {
                if (!TryParseViewportPreviewUri(uri, out var previewFileName))
                    return BuildPlainText404($"Invalid viewport preview URI: {uri.AbsolutePath}");

                var previewPath = Path.Combine(GetViewportPreviewRoot(), previewFileName);
                if (!File.Exists(previewPath))
                    return BuildPlainText404($"Viewport preview not found: {previewFileName}");

                try
                {
                    // FileShare.Delete: a streamed preview must never pin
                    // its file against deletion (issue #241 follow-up).
                    var previewStream = new FileStream(
                        previewPath, FileMode.Open, FileAccess.Read,
                        FileShare.Read | FileShare.Delete);
                    return new VirtualResource(
                        previewStream, "image/png", 200,
                        extraHeaders: "Cache-Control: no-store");
                }
                catch (Exception ex)
                {
                    Log($"Rook: viewport preview stream open failed for {previewPath}: {ex.Message}");
                    return BuildPlainText404("Viewport preview unavailable.");
                }
            }

            if (!TryParseBlobUri(uri, out var artifactId, out var role))
            {
                // Not a blob URI — let the substrate fall through to the
                // embedded-resource lookup.
                if (!IsBlobPath(uri)) return null;

                // Path-shape was blob/... but segments didn't pass
                // validation. Return a 404 explicitly so the browser
                // console surfaces the misuse instead of falling through
                // to an embedded-resource "not found" that obscures the
                // real issue.
                return BuildPlainText404($"Invalid blob URI: {uri.AbsolutePath}");
            }

            string absPath;
            try
            {
                absPath = _artifactStore.GetBlobAbsolutePath(artifactId, role);
            }
            catch (KeyNotFoundException)
            {
                return BuildPlainText404($"Artifact or role not found: {artifactId:D}/{role}");
            }
            catch (FileNotFoundException)
            {
                return BuildPlainText404($"Blob missing on disk for: {artifactId:D}/{role}");
            }
            catch (InvalidDataException ex)
            {
                // Corrupt manifest — serve 404, log the cause for operators.
                Log($"Rook: blob resolution failed for {artifactId:D}/{role}: {ex.Message}");
                return BuildPlainText404("Artifact data is corrupted.");
            }
            catch (ArgumentException)
            {
                // Role failed the store's pattern check. We already
                // validated in TryParseBlobUri, so this is defense-
                // in-depth; treat as 404.
                return BuildPlainText404($"Invalid blob role: {role}");
            }
            catch (Exception ex)
            {
                // Any other exception is unexpected — log and 404 rather
                // than letting it bubble back through the substrate.
                Log($"Rook: blob resolution unexpected error for {artifactId:D}/{role}: {ex.Message}");
                return BuildPlainText404("Blob resolution failed.");
            }

            Stream stream;
            try
            {
                // FileShare.Delete: the gallery renders thumbnails from
                // these streams — without delete sharing, a visible
                // artifact could never be deleted (issue #241 follow-up).
                stream = new FileStream(
                    absPath, FileMode.Open, FileAccess.Read,
                    FileShare.Read | FileShare.Delete);
            }
            catch (Exception ex)
            {
                Log($"Rook: blob stream open failed for {absPath}: {ex.Message}");
                return BuildPlainText404("Blob unavailable.");
            }

            var contentType = GuessBlobContentType(absPath);
            // no-store keeps the browser from caching user-specific blob
            // content; artifacts can be deleted between requests and a
            // cached stale preview would mislead the gallery.
            return new VirtualResource(
                stream, contentType, 200,
                extraHeaders: "Cache-Control: no-store");
        }

        /// <summary>
        /// Cheap path-shape predicate — does the URI start with /blob/?
        /// Used to decide 404-vs-fallthrough when detailed parsing fails.
        /// </summary>
        internal static bool IsBlobPath(Uri uri)
        {
            var trimmed = uri.AbsolutePath.TrimStart('/');
            return trimmed.StartsWith("blob/", StringComparison.Ordinal)
                || trimmed.Equals("blob", StringComparison.Ordinal);
        }

        internal static bool IsViewportPreviewPath(Uri uri)
        {
            var trimmed = uri.AbsolutePath.TrimStart('/');
            return trimmed.StartsWith("viewport-preview/", StringComparison.Ordinal)
                || trimmed.Equals("viewport-preview", StringComparison.Ordinal);
        }

        /// <summary>
        /// Validate a <c>/blob/{artifact_id}/{role}</c> URI. Returns
        /// false for any shape deviation — 3 segments exactly, first
        /// literal <c>blob</c>, second a GUID in "D" form, third matching
        /// the artifact role pattern (<c>^[a-z0-9][a-z0-9_-]*$</c>).
        /// </summary>
        internal static bool TryParseBlobUri(Uri uri, out Guid artifactId, out string role)
        {
            artifactId = Guid.Empty;
            role = string.Empty;

            var absPath = uri.AbsolutePath;
            if (string.IsNullOrEmpty(absPath)) return false;

            var segments = absPath.TrimStart('/').Split('/');
            if (segments.Length != 3) return false;
            if (!string.Equals(segments[0], "blob", StringComparison.Ordinal)) return false;

            if (!Guid.TryParseExact(segments[1], "D", out artifactId)) return false;

            var candidateRole = segments[2];
            if (!IsValidRole(candidateRole)) return false;

            role = candidateRole;
            return true;
        }

        internal static bool TryParseViewportPreviewUri(Uri uri, out string fileName)
        {
            fileName = string.Empty;

            var absPath = uri.AbsolutePath;
            if (string.IsNullOrEmpty(absPath)) return false;

            var segments = absPath.TrimStart('/').Split('/');
            if (segments.Length != 2) return false;
            if (!string.Equals(segments[0], "viewport-preview", StringComparison.Ordinal))
                return false;

            var candidate = segments[1];
            if (candidate.Length != "viewport_yyyyMMdd_HHmmss_fff.png".Length)
                return false;
            if (!candidate.StartsWith("viewport_", StringComparison.Ordinal))
                return false;
            if (!candidate.EndsWith(".png", StringComparison.Ordinal))
                return false;

            var timestamp = candidate.Substring(
                "viewport_".Length,
                "yyyyMMdd_HHmmss_fff".Length);
            for (int i = 0; i < timestamp.Length; i++)
            {
                var c = timestamp[i];
                if (i == 8 || i == 15)
                {
                    if (c != '_') return false;
                }
                else if (!char.IsDigit(c))
                {
                    return false;
                }
            }

            fileName = candidate;
            return true;
        }

        internal static string GetViewportPreviewRoot()
            => Path.Combine(Path.GetTempPath(), "rook", "viewports");

        /// <summary>
        /// Mirror the artifact-store role pattern — lowercase start,
        /// then lowercase alphanumerics / underscores / hyphens. No
        /// path separators, no traversal tokens, no dots.
        /// </summary>
        internal static bool IsValidRole(string role)
        {
            if (string.IsNullOrEmpty(role)) return false;
            if (role.Length > 64) return false; // defensive upper bound

            char first = role[0];
            if (!(char.IsDigit(first) || (first >= 'a' && first <= 'z'))) return false;

            for (int i = 1; i < role.Length; i++)
            {
                char c = role[i];
                bool ok = char.IsDigit(c)
                    || (c >= 'a' && c <= 'z')
                    || c == '_'
                    || c == '-';
                if (!ok) return false;
            }
            return true;
        }

        internal static string GuessBlobContentType(string path)
        {
            var ext = Path.GetExtension(path).ToLowerInvariant();
            return ext switch
            {
                ".png" => "image/png",
                ".jpg" or ".jpeg" => "image/jpeg",
                ".webp" => "image/webp",
                ".gif" => "image/gif",
                ".bmp" => "image/bmp",
                // PR-V3: video kinds. Without these, generated_video
                // blobs would be served as application/octet-stream and
                // browser <video> would refuse to play them.
                ".mp4" => "video/mp4",
                ".mov" => "video/quicktime",
                ".webm" => "video/webm",
                ".json" => "application/json; charset=utf-8",
                ".txt" => "text/plain; charset=utf-8",
                _ => "application/octet-stream",
            };
        }

        internal static VirtualResource BuildPlainText404(string message)
        {
            var bytes = System.Text.Encoding.UTF8.GetBytes(message);
            return new VirtualResource(
                new MemoryStream(bytes),
                "text/plain; charset=utf-8",
                404,
                extraHeaders: "Cache-Control: no-store");
        }
    }
}
