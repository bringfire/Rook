using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using Rhino;
using Rhino.Commands;
using Rhino.PlugIns;
using Rhino.UI;
using Rook.InternalBridge;
using Rook.Services.Vision.Video;
using Rook.Startup;
using Rook.UI.Chat;

namespace Rook
{
    /// <summary>
    /// Rook plugin - enables AI to interact with Rhino 3D via HTTP.
    /// </summary>
    public class RookPlugin : PlugIn
    {
        private const int BridgeRetryLimit = 120;
        private static readonly TimeSpan BridgeRetryInterval = TimeSpan.FromMilliseconds(250);

        private static RookPlugin? _instance;
        private readonly CompanionStartupGate _startupGate =
            new(requiredStableIdleTicks: 2);
        private bool _serverStarted = false;
        private bool _isRhinoInside = false;
        private int _startupRunInProgress = 0;
        private int _bridgeRetryCount = 0;
        private DateTime _nextBridgeRetryUtc = DateTime.MinValue;
        private bool _documentOpening = false;
        private bool _documentOpenInitialViewReady = false;
        private bool _startupHooksAttached = false;
        private bool _shutdownStarted = false;
        private bool _deferredLocalStartupComplete = false;
        private bool _startupComplete = false;
        private bool _bridgeRegistered = false;
        private bool _panelsRegistered = false;
        private DateTimeOffset _onLoadUtc = DateTimeOffset.MinValue;
        private DateTimeOffset? _startupCompleteUtc;
        private string? _lastStartupGateTraceKey;
        private int _lastStartupGateTraceRepeatCount = 0;
        private static readonly string StartupTracePath =
            Path.Combine(RookPaths.DiscoveryFolder, "companion-startup.log");

        public RookPlugin()
        {
            _instance = this;
            TraceStartup("constructor");
        }

        /// <summary>Gets the only instance of the RookPlugin plug-in.</summary>
        public static RookPlugin Instance => _instance!;

        /// <summary>
        /// Companion mode should not present itself as a startup plugin.
        /// RookNative explicitly activates this plugin when GH support is needed.
        /// </summary>
        public override PlugInLoadTime LoadTime => PlugInLoadTime.WhenNeeded;

        /// <summary>
        /// Called when the plugin is loaded.
        /// </summary>
        protected override LoadReturnCode OnLoad(ref string errorMessage)
        {
            _onLoadUtc = DateTimeOffset.UtcNow;
            TraceStartup("OnLoad minimal");

            _isRhinoInside = Rhino.Runtime.HostUtils.RunningAsRhinoInside;
            RookSubsystemRoot.Instance.ConfigureVertexAccessTokenSource(
                ChatServiceVertexAccessTokenSource.Instance);
            AttachStartupGateHooks();
            WriteCompanionRuntimeStatus();

            // NOTE on RookBlockBasePointUserData: the class exists for native
            // side storage/read and for cross-language binary-format contract.
            // In RhinoCommon 8.0.23304, InstanceDefinition.UserData does NOT
            // expose plugin-defined custom UserData instances attached on the
            // native side — diagnosed during #28 Phase C:
            //   * idef.UserData.Contains(UUID) returns true (slot present),
            //   * idef.UserData[i] returns null (no managed wrapper), and
            //   * idef.UserData.Add(managed_ud) returns false.
            // UserData.RegisterType (internal) did not change this. So
            // managed reads fall through to the reflection-bridge legacy
            // user-string path — graceful-degrade, zero behavior change vs
            // PR #30. If a future SDK exposes the missing surface, managed
            // new-first reads start working without further code changes.
            // Any deeper managed-side migration belongs in follow-up #34.

            return LoadReturnCode.Success;
        }

        internal static bool ShouldRegisterStartupPanels(bool isRhinoInside)
        {
            // Panels are supported in both standalone Rhino and Rhino.Inside;
            // only Rhino toolbar loading is suppressed for Rhino.Inside.
            return true;
        }

        private void RegisterStartupPanels()
        {
            try
            {
                // Register the Rook Chat panel (interactive AI chat)
                var chatPanelType = typeof(UI.Chat.RookChatPanel);
                Panels.RegisterPanel(this, chatPanelType, "Rook Chat",
                    System.Drawing.SystemIcons.Information,
                    PanelType.PerDoc);

                // Register the Rook Vision panel (AI image/video UI)
                var visionPanelType = typeof(UI.Vision.RookVisionPanel);
                Panels.RegisterPanel(this, visionPanelType, "Rook Vision",
                    System.Drawing.SystemIcons.Information,
                    PanelType.PerDoc);

                // Register the Knowledge Graph panel (WebUI module)
                var kgPanelType = typeof(UI.Knowledge.KnowledgeGraphPanel);
                Panels.RegisterPanel(this, kgPanelType, "Knowledge Graph",
                    System.Drawing.SystemIcons.Information,
                    PanelType.PerDoc);
                _panelsRegistered = true;
            }
            catch (Exception ex)
            {
                _panelsRegistered = false;
                TraceStartup($"Panel registration failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
                RhinoApp.WriteLine(
                    "Rook: panel registration failed; continuing without companion panels. " +
                    $"Reason: {ex.GetType().Name}.");
            }
        }

        private void AttachStartupGateHooks()
        {
            if (_startupHooksAttached)
            {
                return;
            }

            RhinoApp.Idle += OnStartupGateIdle;
            RhinoDoc.BeginOpenDocument += OnBeginOpenDocument;
            RhinoDoc.EndOpenDocument += OnEndOpenDocument;
            RhinoDoc.EndOpenDocumentInitialViewUpdate += OnEndOpenDocumentInitialViewUpdate;
            _startupHooksAttached = true;
        }

        private void DetachStartupGateHooks()
        {
            if (!_startupHooksAttached)
            {
                return;
            }

            RhinoApp.Idle -= OnStartupGateIdle;
            RhinoDoc.BeginOpenDocument -= OnBeginOpenDocument;
            RhinoDoc.EndOpenDocument -= OnEndOpenDocument;
            RhinoDoc.EndOpenDocumentInitialViewUpdate -= OnEndOpenDocumentInitialViewUpdate;
            _startupHooksAttached = false;
            TraceStartup("StartupGate hooks detached");
        }

        private void OnBeginOpenDocument(object? sender, DocumentOpenEventArgs e)
        {
            _documentOpening = true;
            _documentOpenInitialViewReady = false;
            TraceStartupThrottled("document-open-begin", "StartupGate document open begin");
        }

        private void OnEndOpenDocument(object? sender, DocumentOpenEventArgs e)
        {
            _documentOpening = false;
            _documentOpenInitialViewReady = false;
            TraceStartupThrottled("document-open-end", "StartupGate document open end");
        }

        private void OnEndOpenDocumentInitialViewUpdate(object? sender, DocumentOpenEventArgs e)
        {
            _documentOpening = false;
            _documentOpenInitialViewReady = true;
            TraceStartupThrottled("document-open-initial-view", "StartupGate document open initial view update");
        }

        private void OnStartupGateIdle(object? sender, EventArgs e)
        {
            if (IsWaitingForBridgeRetry())
            {
                return;
            }

            var snapshot = new CompanionStartupGateSnapshot(
                CommandActive: IsRhinoCommandActive(),
                DocumentOpening: IsDocumentOpenLifecycleBlocking(),
                ShutdownStarted: _shutdownStarted);
            var decision = _startupGate.EvaluateIdle(snapshot);

            TraceStartupGateDecision(snapshot, decision);

            if (decision.Action != CompanionStartupGateAction.RunStartup)
            {
                return;
            }

            RunDeferredStartupFromIdle();
        }

        private bool IsWaitingForBridgeRetry()
        {
            if (!_deferredLocalStartupComplete || _nextBridgeRetryUtc == DateTime.MinValue)
            {
                return false;
            }

            var nowUtc = DateTime.UtcNow;
            if (nowUtc < _nextBridgeRetryUtc)
            {
                TraceStartupThrottled(
                    "bridge-retry-wait",
                    "StartupGate bridge retry waiting for throttle interval");
                return true;
            }

            _nextBridgeRetryUtc = DateTime.MinValue;
            _startupGate.MarkStartupAvailableForRetry();
            return false;
        }

        private static bool IsRhinoCommandActive()
        {
            try
            {
                if (RhinoApp.InCommand > 0)
                {
                    return true;
                }
            }
            catch
            {
                return true;
            }

            try
            {
                if (RhinoDoc.ActiveDoc?.IsCommandRunning == true)
                {
                    return true;
                }
            }
            catch
            {
                return true;
            }

            try
            {
                if (Command.InCommand())
                {
                    return true;
                }
            }
            catch
            {
                return true;
            }

            return false;
        }

        private bool IsDocumentOpenLifecycleBlocking()
        {
            if (_documentOpening)
            {
                return true;
            }

            if (IsActiveDocumentOpenLifecycleBlocking())
            {
                return true;
            }

            // If this plugin loaded after BeginOpenDocument already fired, we may
            // never see the begin event. While Rhino still reports a command active
            // and no initial view update has been observed, avoid assuming the
            // document-open lifecycle is stable.
            if (!_documentOpenInitialViewReady && IsRhinoCommandActive())
            {
                return true;
            }

            return false;
        }

        private static bool IsActiveDocumentOpenLifecycleBlocking()
        {
            try
            {
                var doc = RhinoDoc.ActiveDoc;
                if (doc == null)
                {
                    return true;
                }

                return doc.IsOpening || doc.IsInitializing || !doc.IsAvailable;
            }
            catch
            {
                return true;
            }
        }

        private void TraceStartupGateDecision(
            CompanionStartupGateSnapshot snapshot,
            CompanionStartupGateDecision decision)
        {
            var key =
                $"blocked={decision.BlockedReason};action={decision.Action};" +
                $"command={snapshot.CommandActive};docOpen={snapshot.DocumentOpening};" +
                $"stable={decision.StableIdleCount}";
            var message =
                $"StartupGate idle attempt: commandActive={snapshot.CommandActive} " +
                $"documentOpening={snapshot.DocumentOpening} " +
                $"stableIdleCount={decision.StableIdleCount} " +
                $"blockedReason={decision.BlockedReason} action={decision.Action}";
            TraceStartupThrottled(key, message);
        }

        private void TraceStartupThrottled(string key, string message)
        {
            if (!string.Equals(_lastStartupGateTraceKey, key, StringComparison.Ordinal))
            {
                _lastStartupGateTraceKey = key;
                _lastStartupGateTraceRepeatCount = 0;
                TraceStartup(message);
                return;
            }

            _lastStartupGateTraceRepeatCount++;
            if (_lastStartupGateTraceRepeatCount % 25 == 0)
            {
                TraceStartup(message + $" repeat={_lastStartupGateTraceRepeatCount}");
            }
        }

        private void RunDeferredStartupFromIdle()
        {
            if (Interlocked.Exchange(ref _startupRunInProgress, 1) == 1)
            {
                return;
            }

            try
            {
                TraceStartup("StartupGate quiescent: running startup");
                if (RunDeferredCompanionStartup())
                {
                    _startupGate.MarkStartupComplete();
                    DetachStartupGateHooks();
                    WriteCompanionRuntimeStatus();
                }
            }
            catch (Exception ex)
            {
                TraceStartup($"Deferred startup failed (will retry): {ex.GetType().Name}: {ex.Message}");
                if (!_shutdownStarted)
                {
                    _startupGate.MarkStartupAvailableForRetry();
                }
                WriteCompanionRuntimeStatus();
            }
            finally
            {
                Interlocked.Exchange(ref _startupRunInProgress, 0);
            }
        }

        private bool RunDeferredCompanionStartup()
        {
            if (!_deferredLocalStartupComplete)
            {
                if (ShouldRegisterStartupPanels(_isRhinoInside))
                {
                    RegisterStartupPanels();
                }
                else
                {
                    TraceStartup("Rhino.Inside mode: startup panel registration skipped");
                }

                if (!_serverStarted)
                {
                    // The C++ native plugin (RookNative) now owns the HTTP server,
                    // session recording, and scene graph.  The C# companion must NOT
                    // start its own HTTP server or SessionRecorder.
                    _serverStarted = true;
                    TraceStartup("Companion UI/runtime startup complete; HTTP server delegated to RookNative");
                }

                try
                {
                    RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();
                    TraceStartup("Video subsystem reconciled (or no-op if never used previously)");
                }
                catch (Exception ex)
                {
                    TraceStartup($"Video reconcile failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
                    RhinoApp.WriteLine(
                        "Rook: video reconcile failed at startup; continuing without reconcile. " +
                        $"Reason: {ex.GetType().Name}.");
                }

                try
                {
                    RookSubsystemRoot.Instance.ReconcileImageJobsOnce();
                    TraceStartup("Image job subsystem reconciled (or no-op)");
                }
                catch (Exception ex)
                {
                    TraceStartup($"Image job reconcile failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
                    RhinoApp.WriteLine(
                        "Rook: image job reconcile failed at startup; continuing without reconcile. " +
                        $"Reason: {ex.GetType().Name}.");
                }

                try
                {
                    RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(
                        new VideoSidecarBackfillStartupOptions(
                            Enabled: true,
                            ServiceOptions: VideoSidecarBackfillOptions.StartupDefault,
                            OnCompleted: result =>
                                TraceStartup($"Video sidecar backfill completed: {result.ToTraceSummary()}"),
                            OnFailed: ex =>
                                TraceStartup($"Video sidecar backfill failed (non-fatal): {ex.GetType().Name}: {ex.Message}")));
                    TraceStartup("Video sidecar backfill scheduled (or no-op if already scheduled)");
                }
                catch (Exception ex)
                {
                    TraceStartup($"Video sidecar backfill scheduling failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
                    RhinoApp.WriteLine(
                        "Rook: video sidecar backfill could not be scheduled at startup; continuing. " +
                        $"Reason: {ex.GetType().Name}.");
                }

                _deferredLocalStartupComplete = true;
                WriteCompanionRuntimeStatus();
            }

            var nowUtc = DateTime.UtcNow;
            if (nowUtc < _nextBridgeRetryUtc)
            {
                return false;
            }

            var nativeBridgeRegistered = NativeGhBridgeRegistrar.TryRegister();
            _bridgeRegistered = nativeBridgeRegistered;
            TraceStartup($"Deferred startup bridgeRegistered={nativeBridgeRegistered} bridgeRetryCount={_bridgeRetryCount}");
            if (!nativeBridgeRegistered)
            {
                _bridgeRetryCount++;
                _nextBridgeRetryUtc = nowUtc + BridgeRetryInterval;
                if (_bridgeRetryCount >= BridgeRetryLimit)
                {
                    TraceStartup("Startup bridge retries exhausted; bridge-dependent features unavailable.");
                    DetachStartupGateHooks();
                    WriteCompanionRuntimeStatus();
                    return true;
                }

                WriteCompanionRuntimeStatus();
                return false;
            }

            TraceStartup("Startup complete");
            _startupComplete = true;
            _startupCompleteUtc = DateTimeOffset.UtcNow;
            WriteCompanionRuntimeStatus();
            return true;
        }

        private void WriteCompanionRuntimeStatus()
        {
            try
            {
                var snapshot = CompanionRuntimeStatus.CreateSnapshot(
                    rhinoInside: _isRhinoInside,
                    startupGateAttached: _startupHooksAttached,
                    deferredLocalStartupComplete: _deferredLocalStartupComplete,
                    startupComplete: _startupComplete,
                    bridgeRegistered: _bridgeRegistered,
                    panelsRegistered: _panelsRegistered,
                    onLoadUtc: _onLoadUtc,
                    startupCompleteUtc: _startupCompleteUtc);
                CompanionRuntimeStatus.Write(snapshot);
            }
            catch (Exception ex)
            {
                TraceStartup($"Companion runtime status write failed (non-fatal): {ex.GetType().Name}: {ex.Message}");
            }
        }

        private static void TraceStartup(string message)
        {
            try
            {
                Directory.CreateDirectory(RookPaths.DiscoveryFolder);
                File.AppendAllText(
                    StartupTracePath,
                    $"{DateTime.Now:O} pid={Process.GetCurrentProcess().Id} {message}{Environment.NewLine}");
            }
            catch
            {
                // Diagnostic only.
            }
        }

        // NOTE: EnsureSessionInitialized() removed — C++ CSessionRecorder owns
        // command tracking.  The C# SessionRecorder must NOT be initialized in
        // companion mode to avoid duplicate Command.BeginCommand/EndCommand handlers.

        /// <summary>
        /// Called when the plugin is unloaded.
        ///
        /// Order of operations matters:
        /// <list type="number">
        ///   <item>Detach startup gate handlers — stops new deferred startup
        ///         calls from racing with the rest of shutdown.</item>
        ///   <item>DetachStartupGateHooks — stops idle/document lifecycle startup callbacks.</item>
        ///   <item>NativeGhBridgeRegistrar.ClearRegistration — removes
        ///         the C++→C# vision_dispatch callback so no new video
        ///         (or image) ops can be routed.</item>
        ///   <item>ChatServiceManager.Shutdown — independent subsystem.</item>
        ///   <item>RookSubsystemRoot.DisposeCreatedSubsystems —
        ///         disposes any lazy subsystem bundles that were built
        ///         (e.g. the VideoJobManager cancels in-flight jobs via
        ///         shutdown CTS and releases resources). After this
        ///         returns, the root rejects further subsystem access
        ///         per its post-dispose contract. No-op for bundles
        ///         never built (e.g. image-only sessions).</item>
        /// </list>
        /// All teardown steps that touch external state are wrapped in
        /// try/catch — a single failure must not abort the others.
        /// </summary>
        protected override void OnShutdown()
        {
            _shutdownStarted = true;
            DetachStartupGateHooks();

            // Codex review of step 7: each external-state teardown step
            // gets its own try/catch. A failure in ClearRegistration
            // (e.g., ABI-bridge cleanup throws) MUST NOT skip chat
            // shutdown, video dispose, or base.OnShutdown — those are
            // independent contracts that all need to fire.
            try
            {
                NativeGhBridgeRegistrar.ClearRegistration();
            }
            catch (Exception ex)
            {
                TraceStartup($"Native GH bridge clear failed: {ex.GetType().Name}: {ex.Message}");
            }

            try
            {
                ChatServiceManager.Instance.Shutdown();
            }
            catch (Exception ex)
            {
                TraceStartup($"Chat service shutdown failed: {ex.GetType().Name}: {ex.Message}");
            }

            // V2: dispose the video subsystem if it was ever built.
            // Idempotent + IsValueCreated-guarded inside the root —
            // image-only sessions pay nothing here, and a double-call
            // (e.g., AppDomain unload race) is safe.
            try
            {
                RookSubsystemRoot.Instance.DisposeCreatedSubsystems();
            }
            catch (Exception ex)
            {
                TraceStartup($"Video subsystem dispose failed: {ex.GetType().Name}: {ex.Message}");
            }

            // NOTE: SessionRecorder and SceneGraph shutdown removed — C++ owns both.
            // The C# companion never initializes these in companion mode.

            base.OnShutdown();
        }
    }
}
