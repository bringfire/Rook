using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using Rhino;
using Rhino.PlugIns;
using Rhino.UI;
using Rook.InternalBridge;
using Rook.Services.Vision.Video;
using Rook.UI.Chat;

namespace Rook
{
    /// <summary>
    /// Rook plugin - enables AI to interact with Rhino 3D via HTTP.
    /// </summary>
    public class RookPlugin : PlugIn
    {
        private const int StartupRetryIntervalMs = 250;
        private const int StartupRetryLimit = 120;

        private static RookPlugin? _instance;
        private bool _serverStarted = false;
        private bool _toolbarLoaded = false;
        private bool _isRhinoInside = false;
        private int _startupRetryCount = 0;
        private Timer? _startupRetryTimer;
        private int _startupInitInProgress = 0;
        private bool _startupRetriesActive = false;
        private static readonly string StartupTracePath =
            Path.Combine(RookPaths.DiscoveryFolder, "companion-startup.log");

        public RookPlugin()
        {
            _instance = this;
            TraceStartup("constructor");
            // Keep Idle hooks for normal Rhino startup, but do not depend on them
            // exclusively when the plugin is autoloaded by RookNative later.
            RhinoApp.Idle += OnRhinoIdle;
            RhinoApp.Idle += EnsureNativeGhBridgeRegistered;
        }

        /// <summary>Gets the only instance of the RookPlugin plug-in.</summary>
        public static RookPlugin Instance => _instance!;

        /// <summary>
        /// Companion mode should not present itself as a startup plugin.
        /// RookNative explicitly activates this plugin when GH support is needed.
        /// </summary>
        public override PlugInLoadTime LoadTime => PlugInLoadTime.WhenNeeded;

        /// <summary>
        /// Start server when Rhino is ready. Idle remains a helpful signal, but
        /// startup also has an explicit retry path for autoloaded companion mode.
        /// </summary>
        private void OnRhinoIdle(object? sender, EventArgs e)
        {
            TryInitializeRuntime();
        }

        private void EnsureNativeGhBridgeRegistered(object? sender, EventArgs e)
        {
            TryInitializeRuntime();
        }

        /// <summary>
        /// Called when the plugin is loaded.
        /// </summary>
        protected override LoadReturnCode OnLoad(ref string errorMessage)
        {
            TraceStartup("OnLoad");

            _isRhinoInside = Rhino.Runtime.HostUtils.RunningAsRhinoInside;
            if (_isRhinoInside)
            {
                TraceStartup("Rhino.Inside mode detected");
                RhinoApp.WriteLine("Rook companion: Rhino.Inside detected — toolbar disabled.");
            }
            else
            {
                RhinoApp.WriteLine("Rook companion loaded. HTTP server will start shortly...");
            }

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

            BeginStartupRetries();
            RhinoApp.InvokeOnUiThread(new Action(TryInitializeRuntime));

            return LoadReturnCode.Success;
        }

        private void BeginStartupRetries()
        {
            TraceStartup("BeginStartupRetries");
            _startupRetryTimer?.Dispose();
            _startupRetryCount = 0;
            _startupRetriesActive = true;
            _startupRetryTimer = new Timer(_ =>
            {
                try
                {
                    RhinoApp.InvokeOnUiThread(new Action(TryInitializeRuntime));
                }
                catch
                {
                    // Ignore transient shutdown/startup races; the next retry or
                    // idle event will try again while Rhino is still alive.
                }
            }, null, Timeout.Infinite, Timeout.Infinite);
            ScheduleNextStartupRetry();
        }

        private void StopStartupRetries()
        {
            _startupRetriesActive = false;
            _startupRetryTimer?.Dispose();
            _startupRetryTimer = null;
        }

        private void ScheduleNextStartupRetry()
        {
            if (!_startupRetriesActive || _startupRetryTimer == null)
            {
                return;
            }

            try
            {
                _startupRetryTimer.Change(StartupRetryIntervalMs, Timeout.Infinite);
            }
            catch (ObjectDisposedException)
            {
                // Shutdown race — safe to ignore.
            }
        }

        private void TryInitializeRuntime()
        {
            if (Interlocked.Exchange(ref _startupInitInProgress, 1) == 1)
            {
                return;
            }

            try
            {
                var nativeBridgeRegistered = NativeGhBridgeRegistrar.TryRegister();
                TraceStartup($"TryInitializeRuntime bridgeRegistered={nativeBridgeRegistered} serverStarted={_serverStarted} retryCount={_startupRetryCount}");

                if (!_serverStarted)
                {
                    // The C++ native plugin (RookNative) now owns the HTTP server,
                    // session recording, and scene graph.  The C# companion must NOT
                    // start its own HTTP server or SessionRecorder — doing so adds a
                    // second set of Command.BeginCommand / EndCommand handlers that
                    // enumerate doc.Objects on every command (including _SaveSmall),
                    // plus a background-thread HTTP server whose handlers can race
                    // with Rhino's file-save serialization.
                    //
                    // The companion's only responsibilities are:
                    //   1. GH bridge registration (NativeGhBridgeRegistrar)
                    //   2. Panel UI (Rook panel, Chat panel)
                    //   3. Toolbar loading
                    _serverStarted = true;
                    RhinoApp.Idle -= OnRhinoIdle;
                    // DO NOT call EnsureSessionInitialized() — C++ CSessionRecorder handles this
                    if (!_isRhinoInside)
                        EnsureToolbarLoaded();
                    RhinoApp.WriteLine("Rook companion loaded (HTTP server + session recording delegated to RookNative).");
                }

                if (nativeBridgeRegistered)
                {
                    // NOTE: RookServer.EnableCompanionMode() was previously called
                    // here, but it's a no-op — the C# HTTP server is never started
                    // in companion mode (IsRunning is always false).  Removed to
                    // avoid confusion.  The C++ native plugin writes the only
                    // discovery file that bridge.py reads.

                    // V2: reconcile any non-terminal video jobs left by a
                    // prior session (per v3.1 D4). The root's
                    // ReconcileVideoJobsOnce is Interlocked-guarded so a
                    // double-call across plugin reload paths is safe.
                    // Reconcile failures are non-fatal — startup continues.
                    // The Interlocked flag inside ReconcileVideoJobsOnce
                    // resets on throw so a future plugin reload retries
                    // fresh.
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

                    RhinoApp.Idle -= EnsureNativeGhBridgeRegistered;
                    StopStartupRetries();
                    TraceStartup("GH bridge registered — companion startup complete");
                    return;
                }

                if (_serverStarted && _startupRetriesActive)
                {
                    _startupRetryCount++;
                    if (_startupRetryCount >= StartupRetryLimit)
                    {
                        StopStartupRetries();
                        RhinoApp.Idle -= EnsureNativeGhBridgeRegistered;
                        TraceStartup("Startup retries exhausted");
                        RhinoApp.WriteLine("Rook: native GH callback bridge was not available after startup retries; staying in companion mode.");
                    }
                    else
                    {
                        ScheduleNextStartupRetry();
                    }
                }
            }
            finally
            {
                Interlocked.Exchange(ref _startupInitInProgress, 0);
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

        private void EnsureToolbarLoaded()
        {
            if (_toolbarLoaded)
            {
                return;
            }

            LoadToolbar();
            _toolbarLoaded = true;
        }

        /// <summary>
        /// Loads the Rook.rui toolbar file if not already open.
        /// </summary>
        private void LoadToolbar()
        {
            try
            {
                // RUI file is copied alongside the .rhp by the build
                var pluginDir = Path.GetDirectoryName(typeof(RookPlugin).Assembly.Location);
                if (string.IsNullOrEmpty(pluginDir)) return;

                var ruiPath = Path.Combine(pluginDir, "Rook.rui");
                if (!File.Exists(ruiPath))
                {
                    RhinoApp.WriteLine("Rook: Toolbar file not found at " + ruiPath);
                    return;
                }

                // Check if already loaded (avoid duplicates on reload)
                var toolbarFiles = RhinoApp.ToolbarFiles;
                for (int i = 0; i < toolbarFiles.Count; i++)
                {
                    var existing = toolbarFiles[i];
                    if (existing != null && existing.Name != null &&
                        existing.Name.Equals("Rook", StringComparison.OrdinalIgnoreCase))
                    {
                        return; // Already loaded
                    }
                }

                toolbarFiles.Open(ruiPath);
                RhinoApp.WriteLine("Rook: Toolbar loaded.");
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine("Rook: Failed to load toolbar - " + ex.Message);
            }
        }

        /// <summary>
        /// Called when the plugin is unloaded.
        ///
        /// Order of operations matters:
        /// <list type="number">
        ///   <item>Detach Idle handlers — stops new TryInitializeRuntime
        ///         calls from racing with the rest of shutdown.</item>
        ///   <item>StopStartupRetries — cancels the background timer.</item>
        ///   <item>NativeGhBridgeRegistrar.ClearRegistration — removes
        ///         the C++→C# vision_dispatch callback so no new video
        ///         (or image) ops can be routed.</item>
        ///   <item>ChatServiceManager.Shutdown — independent subsystem.</item>
        ///   <item>RookSubsystemRoot.DisposeVideoSubsystemIfCreated —
        ///         disposes the VideoJobManager (cancels in-flight
        ///         jobs via shutdown CTS, releases resources). After
        ///         this returns, the root rejects further Video access
        ///         per its post-dispose contract. No-op when video was
        ///         never built (image-only sessions).</item>
        /// </list>
        /// All teardown steps that touch external state are wrapped in
        /// try/catch — a single failure must not abort the others.
        /// </summary>
        protected override void OnShutdown()
        {
            RhinoApp.Idle -= OnRhinoIdle;
            RhinoApp.Idle -= EnsureNativeGhBridgeRegistered;
            StopStartupRetries();

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
                RookSubsystemRoot.Instance.DisposeVideoSubsystemIfCreated();
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
