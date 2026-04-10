using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using Rhino;
using Rhino.PlugIns;
using Rhino.UI;
using Rook.InternalBridge;
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

            // Register the Rook Chat panel (interactive AI chat)
            var chatPanelType = typeof(UI.Chat.RookChatPanel);
            Panels.RegisterPanel(this, chatPanelType, "Rook Chat",
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
            }, null, StartupRetryIntervalMs, StartupRetryIntervalMs);
        }

        private void StopStartupRetries()
        {
            _startupRetryTimer?.Dispose();
            _startupRetryTimer = null;
        }

        private void TryInitializeRuntime()
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
                RhinoApp.Idle -= EnsureNativeGhBridgeRegistered;
                StopStartupRetries();
                TraceStartup("GH bridge registered — companion startup complete");
                return;
            }

            if (_serverStarted)
            {
                _startupRetryCount++;
                if (_startupRetryCount >= StartupRetryLimit)
                {
                    StopStartupRetries();
                    RhinoApp.Idle -= EnsureNativeGhBridgeRegistered;
                    TraceStartup("Startup retries exhausted");
                    RhinoApp.WriteLine("Rook: native GH callback bridge was not available after startup retries; staying in companion mode.");
                }
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
        /// </summary>
        protected override void OnShutdown()
        {
            RhinoApp.Idle -= OnRhinoIdle;
            RhinoApp.Idle -= EnsureNativeGhBridgeRegistered;
            StopStartupRetries();
            NativeGhBridgeRegistrar.ClearRegistration();
            ChatServiceManager.Instance.Shutdown();

            // NOTE: SessionRecorder and SceneGraph shutdown removed — C++ owns both.
            // The C# companion never initializes these in companion mode.

            base.OnShutdown();
        }
    }
}
