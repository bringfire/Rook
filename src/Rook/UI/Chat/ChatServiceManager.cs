using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Rhino;

namespace Rook.UI.Chat
{
    public class ChatServiceManifest
    {
        [JsonPropertyName("pythonPath")]
        public string PythonPath { get; set; } = "";

        [JsonPropertyName("workingDirectory")]
        public string WorkingDirectory { get; set; } = "";

        [JsonPropertyName("module")]
        public string Module { get; set; } = "rook.agent.chat.service_main";

        [JsonPropertyName("pythonPathEntries")]
        public List<string> PythonPathEntries { get; set; } = new List<string>();

        [JsonPropertyName("environment")]
        public Dictionary<string, string> Environment { get; set; } = new Dictionary<string, string>();

        [JsonPropertyName("owner")]
        public string Owner { get; set; } = "rhino-panel";
    }

    internal readonly struct ChatServiceRuntimeValidation
    {
        public ChatServiceRuntimeValidation(
            bool isValid,
            string message,
            bool isTerminalInvalidManifest)
        {
            IsValid = isValid;
            Message = message ?? "";
            IsTerminalInvalidManifest = isTerminalInvalidManifest;
        }

        public bool IsValid { get; }
        public string Message { get; }
        public bool IsTerminalInvalidManifest { get; }

        public static ChatServiceRuntimeValidation Valid =>
            new ChatServiceRuntimeValidation(true, "", false);
    }

    internal enum ChatServiceStartDecision
    {
        ReuseHealthyService,
        RestartBecauseNonceMissing,
        WaitForTrackedProcess,
        StartNewProcess,
    }

    public class ChatServiceHealth
    {
        public bool ServiceAvailable { get; set; }
        public string ServiceMessage { get; set; } = "";
        public Uri? BaseUri { get; set; }
        public bool RuntimeAvailable { get; set; }
        public bool RhinoConnected { get; set; }
        public bool PromptAvailable { get; set; }
        public bool PromptActive { get; set; }
        public string PromptText { get; set; } = "";
        public bool LlmConfigured { get; set; }
        public string LlmMessage { get; set; } = "";
    }

    internal class ChatServiceDiscoveryRecord
    {
        [JsonPropertyName("service")]
        public string Service { get; set; } = "";

        [JsonPropertyName("host")]
        public string Host { get; set; } = "127.0.0.1";

        [JsonPropertyName("port")]
        public int Port { get; set; }

        [JsonPropertyName("owner")]
        public string Owner { get; set; } = "";

        [JsonPropertyName("pid")]
        public int Pid { get; set; }

        [JsonPropertyName("rhinoProcessId")]
        public int RhinoProcessId { get; set; }
    }

    internal class ChatServiceHealthEnvelope
    {
        [JsonPropertyName("service")]
        public ChatServiceHealthService? Service { get; set; }

        [JsonPropertyName("runtime")]
        public ChatServiceHealthRuntime? Runtime { get; set; }
    }

    internal class ChatServiceHealthService
    {
        [JsonPropertyName("status")]
        public string Status { get; set; } = "";

        [JsonPropertyName("ok")]
        public bool Ok { get; set; }

        [JsonPropertyName("host")]
        public string Host { get; set; } = "127.0.0.1";

        [JsonPropertyName("port")]
        public int Port { get; set; }

        [JsonPropertyName("owner")]
        public string? Owner { get; set; }

        [JsonPropertyName("rhinoProcessId")]
        public int RhinoProcessId { get; set; }
    }

    internal class ChatServiceHealthRuntime
    {
        [JsonPropertyName("available")]
        public bool Available { get; set; }

        [JsonPropertyName("rhino")]
        public ChatServiceRhinoState? Rhino { get; set; }

        [JsonPropertyName("prompt")]
        public ChatServicePromptState? Prompt { get; set; }

        [JsonPropertyName("llm")]
        public ChatServiceLlmState? Llm { get; set; }
    }

    internal class ChatServiceRhinoState
    {
        [JsonPropertyName("connected")]
        public bool Connected { get; set; }

        [JsonPropertyName("data")]
        public object? Data { get; set; }
    }

    internal class ChatServicePromptState
    {
        [JsonPropertyName("available")]
        public bool Available { get; set; }

        [JsonPropertyName("is_active")]
        public bool IsActive { get; set; }

        [JsonPropertyName("prompt")]
        public string? Prompt { get; set; }
    }

    internal class ChatServiceLlmState
    {
        [JsonPropertyName("configured")]
        public bool Configured { get; set; }

        [JsonPropertyName("message")]
        public string? Message { get; set; }
    }

    /// <summary>
    /// Rhino-owned lifecycle manager for the local Agent Chat Python service.
    /// </summary>
    public sealed class ChatServiceManager
    {
        private static readonly Lazy<ChatServiceManager> _lazy =
            new Lazy<ChatServiceManager>(() => new ChatServiceManager());

        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        private readonly SemaphoreSlim _gate = new SemaphoreSlim(1, 1);
        private readonly HttpClient _httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(8)
        };

        private static readonly TimeSpan StartupTimeout = TimeSpan.FromSeconds(60);
        private static readonly TimeSpan StartupPollInterval = TimeSpan.FromMilliseconds(250);
        private static readonly TimeSpan ShutdownGateTimeout = TimeSpan.FromSeconds(5);

        private Process? _ownedProcess;
        private CancellationTokenSource? _logTailerCts;

        private const string ExpectedOwner = "rhino-panel";
        private const string NonceEnvVar = "ROOK_SESSION_NONCE";

        /// <summary>
        /// Per-chat-server-lifetime bearer token. Generated when the C# host
        /// starts the Python chat service; passed via environment variable.
        /// Required as <c>X-Rook-Session</c> header on all chat-server routes.
        /// Not persisted in discovery files.
        /// </summary>
        public string? SessionNonce { get; private set; }

        private static int CurrentRhinoProcessId => Process.GetCurrentProcess().Id;

        private ChatServiceManager()
        {
        }

        public static ChatServiceManager Instance => _lazy.Value;

        public async Task<ChatServiceHealth> EnsureStartedAsync(CancellationToken ct = default)
        {
            await _gate.WaitAsync(ct);
            try
            {
                // Clean up stale discovery files from crashed sessions BEFORE
                // attempting to resolve.  Without this, ResolveHealthyBaseUriAsync
                // can latch onto a dead process's file and waste the full timeout.
                CleanupStaleChatDiscoveryFiles();

                var existing = await GetHealthInternalAsync(startIfNeeded: false, ct: ct);
                var startDecision = ShouldStartChatService(
                    trackedProcessExists: _ownedProcess != null,
                    trackedProcessHasExited: _ownedProcess?.HasExited ?? true,
                    existingServiceAvailable: existing.ServiceAvailable,
                    sessionNoncePresent: !string.IsNullOrEmpty(SessionNonce));
                if (startDecision == ChatServiceStartDecision.ReuseHealthyService)
                {
                    // Session nonce is still valid — reuse the running service.
                    return existing;
                }

                if (startDecision == ChatServiceStartDecision.RestartBecauseNonceMissing)
                {
                    // Service is running but we lost the nonce (companion reload,
                    // panel recreation, etc.).  The Python process still enforces
                    // the old nonce, so every non-health request would 403.  Stop
                    // it and let the normal start path generate a fresh nonce.
                    RhinoApp.WriteLine("Rook: restarting chat service — session nonce lost after companion reload");
                    StopOwnedProcess();
                    StopDiscoveredOwnedService();
                }

                var manifest = LoadManifest();
                if (manifest == null)
                {
                    return new ChatServiceHealth
                    {
                        ServiceAvailable = false,
                        ServiceMessage =
                            "Chat service manifest (RookChatService.json) not found and auto-generation failed. "
                            + "Run: scripts\\register-rooknative-suite.ps1  or  "
                            + "scripts\\write-chat-service-manifest.ps1 -PluginDir <plugin-dir> "
                            + "-PythonPath <python.exe> -WorkingDirectory <mcp_server-dir>",
                    };
                }

                var runtimeValidation = ValidateManifestRuntime(manifest);
                if (!runtimeValidation.IsValid)
                {
                    return new ChatServiceHealth
                    {
                        ServiceAvailable = false,
                        ServiceMessage = runtimeValidation.Message,
                    };
                }

                StartProcess(manifest);

                var started = await WaitForHealthyServiceAsync(ct);
                if (started != null)
                {
                    return started;
                }

                return new ChatServiceHealth
                {
                    ServiceAvailable = false,
                    ServiceMessage = $"Chat service failed to start within {StartupTimeout.TotalSeconds:0} seconds.",
                };
            }
            finally
            {
                _gate.Release();
            }
        }

        public async Task<ChatServiceHealth> GetHealthAsync(bool startIfNeeded, CancellationToken ct = default)
        {
            if (!startIfNeeded)
            {
                await _gate.WaitAsync(ct);
                try
                {
                    return await GetHealthInternalAsync(startIfNeeded: false, ct: ct);
                }
                finally
                {
                    _gate.Release();
                }
            }

            return await EnsureStartedAsync(ct);
        }

        public async Task<ChatServiceHealth> GetHealthForBaseUriAsync(Uri baseUri, CancellationToken ct = default)
        {
            await _gate.WaitAsync(ct);
            try
            {
                var health = await QueryHealthAsync(baseUri, ct);
                if (health != null)
                {
                    return health;
                }

                return new ChatServiceHealth
                {
                    ServiceAvailable = false,
                    ServiceMessage = $"Chat service did not respond correctly at {baseUri}.",
                    BaseUri = baseUri,
                };
            }
            finally
            {
                _gate.Release();
            }
        }

        public async Task<ChatServiceHealth> RestartAsync(CancellationToken ct = default)
        {
            await _gate.WaitAsync(ct);
            try
            {
                StopOwnedProcess();
                StopDiscoveredOwnedService();
            }
            finally
            {
                _gate.Release();
            }
            return await EnsureStartedAsync(ct);
        }

        public void Shutdown()
        {
            var entered = false;
            try
            {
                entered = _gate.Wait(ShutdownGateTimeout);
                if (!entered)
                {
                    RhinoApp.WriteLine("Rook: chat service shutdown skipped semaphore wait after timeout; proceeding with best-effort cleanup.");
                }
                ConversationCloseCoordinator.Instance
                    .DrainAsync(ShutdownGateTimeout)
                    .GetAwaiter()
                    .GetResult();
                StopServicesBestEffort();
            }
            finally
            {
                if (entered)
                    _gate.Release();
            }
        }

        private async Task<ChatServiceHealth> GetHealthInternalAsync(bool startIfNeeded, CancellationToken ct)
        {
            var baseUri = await ResolveHealthyBaseUriAsync(ct);
            if (baseUri == null)
            {
                return new ChatServiceHealth
                {
                    ServiceAvailable = false,
                    ServiceMessage = startIfNeeded
                        ? "Chat service is not running."
                        : "Chat service is unavailable.",
                };
            }

            var health = await QueryHealthAsync(baseUri, ct);
            if (health != null)
            {
                return health;
            }

            return new ChatServiceHealth
            {
                ServiceAvailable = false,
                ServiceMessage = $"Chat service did not respond correctly at {baseUri}.",
            };
        }

        internal static string ResolveManifestPath(string assemblyLocation)
        {
            var pluginDir = Path.GetDirectoryName(assemblyLocation) ?? "";
            return Path.Combine(pluginDir, "RookChatService.json");
        }

        private static string GetManifestPath()
        {
            return ResolveManifestPath(typeof(ChatServiceManager).Assembly.Location);
        }

        internal static ChatServiceRuntimeValidation ValidateManifestRuntime(ChatServiceManifest manifest)
        {
            if (!File.Exists(manifest.PythonPath))
            {
                return new ChatServiceRuntimeValidation(
                    false,
                    $"Python runtime not found: {manifest.PythonPath}",
                    true);
            }

            if (!Directory.Exists(manifest.WorkingDirectory))
            {
                return new ChatServiceRuntimeValidation(
                    false,
                    $"Chat service working directory not found: {manifest.WorkingDirectory}",
                    false);
            }

            if (!string.Equals(manifest.Owner, ExpectedOwner, StringComparison.OrdinalIgnoreCase))
            {
                return new ChatServiceRuntimeValidation(
                    false,
                    $"Unsupported chat service owner '{manifest.Owner}'. Expected '{ExpectedOwner}'.",
                    false);
            }

            return ChatServiceRuntimeValidation.Valid;
        }

        internal static ChatServiceStartDecision ShouldStartChatService(
            bool trackedProcessExists,
            bool trackedProcessHasExited,
            bool existingServiceAvailable,
            bool sessionNoncePresent)
        {
            if (existingServiceAvailable)
            {
                return sessionNoncePresent
                    ? ChatServiceStartDecision.ReuseHealthyService
                    : ChatServiceStartDecision.RestartBecauseNonceMissing;
            }

            if (trackedProcessExists && !trackedProcessHasExited)
            {
                return ChatServiceStartDecision.WaitForTrackedProcess;
            }

            return ChatServiceStartDecision.StartNewProcess;
        }

        private static string GetDiscoveryFolder()
        {
            return RookPaths.DiscoveryFolder;
        }

        private static IEnumerable<string> GetDiscoveryFiles()
        {
            var folder = GetDiscoveryFolder();
            if (!Directory.Exists(folder))
            {
                return Enumerable.Empty<string>();
            }

            return Directory.GetFiles(folder, "chat-service-*.json")
                .OrderByDescending(File.GetLastWriteTimeUtc);
        }

        private static bool IsCurrentRhinoRecord(ChatServiceDiscoveryRecord record)
        {
            return record.RhinoProcessId == CurrentRhinoProcessId;
        }

        private static IEnumerable<(string Path, ChatServiceDiscoveryRecord Record)> GetOwnedDiscoveryRecords()
        {
            foreach (var file in GetDiscoveryFiles())
            {
                ChatServiceDiscoveryRecord? record = null;
                try
                {
                    var json = File.ReadAllText(file);
                    record = JsonSerializer.Deserialize<ChatServiceDiscoveryRecord>(json, JsonOptions);
                }
                catch
                {
                    // Ignore stale or malformed discovery files.
                }

                if (record == null
                    || !string.Equals(record.Service, "agent-chat", StringComparison.OrdinalIgnoreCase)
                    || !string.Equals(record.Owner, ExpectedOwner, StringComparison.OrdinalIgnoreCase)
                    || !IsCurrentRhinoRecord(record))
                {
                    continue;
                }

                yield return (file, record);
            }
        }

        private ChatServiceManifest? LoadManifest()
        {
            try
            {
                var manifestPath = GetManifestPath();
                if (File.Exists(manifestPath))
                {
                    var json = File.ReadAllText(manifestPath);
                    var manifest = JsonSerializer.Deserialize<ChatServiceManifest>(json, JsonOptions);
                    if (manifest != null)
                    {
                        var runtimeValidation = ValidateManifestRuntime(manifest);
                        if (!runtimeValidation.IsValid && runtimeValidation.IsTerminalInvalidManifest)
                        {
                            RhinoApp.WriteLine(
                                "Rook: chat service manifest is invalid "
                                + $"({runtimeValidation.Message}).");
                            return manifest;
                        }

                        if (IsManifestCurrent(manifest, out var staleReason))
                        {
                            return manifest;
                        }

                        RhinoApp.WriteLine(
                            "Rook: cached chat service manifest is stale "
                            + $"({staleReason}). Regenerating.");
                    }
                }

                // Manifest missing or stale — try to auto-generate from .mcp.json
                var generated = TryAutoGenerateManifest(manifestPath);
                if (generated != null)
                {
                    RhinoApp.WriteLine($"Rook: auto-generated chat service manifest at {manifestPath}");
                    return generated;
                }

                RhinoApp.WriteLine(
                    "Rook: chat service manifest not found and could not be auto-generated. "
                    + "Run scripts\\write-chat-service-manifest.ps1 or scripts\\register-rooknative-suite.ps1.");
                return null;
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook chat service manifest load failed: {ex.Message}");
                return null;
            }
        }

        /// <summary>
        /// Attempts to auto-generate the RookChatService.json manifest.
        ///
        /// Discovery strategies (in priority order):
        ///   1. ROOK_PROJECT_ROOT env var → .mcp.json
        ///   2. Plugin-relative repo detection (assembly dir → ancestor with .mcp.json)
        ///   3. Release install root (%LOCALAPPDATA%\Rook\app\mcp_server)
        ///   4. pip-installed rook package (python -c "import rook; ...")
        ///   5. PATH-based Python discovery (where python, py launcher)
        ///
        /// Designed to work on any machine — no hardcoded developer paths.
        /// </summary>
        private static ChatServiceManifest? TryAutoGenerateManifest(string manifestPath)
        {
            try
            {
                string? pythonPath = null;
                string? workingDirectory = null;

                // Collect candidate repo roots (no hardcoded paths — all derived)
                var candidates = new List<string>();

                // 1. Explicit env var
                var projectRoot = Environment.GetEnvironmentVariable("ROOK_PROJECT_ROOT");
                if (!string.IsNullOrEmpty(projectRoot) && Directory.Exists(projectRoot))
                    candidates.Add(projectRoot);

                // 2. Walk up from the plugin assembly to find the repo root.
                //    Works for both dev builds (src/Rook/bin/Debug/net7.0/) and
                //    deployed layouts where the repo is an ancestor of the plugin dir.
                var pluginDir = Path.GetDirectoryName(typeof(ChatServiceManager).Assembly.Location);
                if (!string.IsNullOrEmpty(pluginDir))
                {
                    var ancestor = new DirectoryInfo(pluginDir);
                    for (int i = 0; i < 8 && ancestor != null; i++, ancestor = ancestor.Parent)
                    {
                        if (File.Exists(Path.Combine(ancestor.FullName, ".mcp.json"))
                            || Directory.Exists(Path.Combine(ancestor.FullName, "mcp_server")))
                        {
                            candidates.Add(ancestor.FullName);
                            break;
                        }
                    }
                }

                var releaseInstallRoot = GetReleaseInstallRoot();
                if (!string.IsNullOrEmpty(releaseInstallRoot)
                    && Directory.Exists(Path.Combine(releaseInstallRoot, "mcp_server")))
                {
                    candidates.Add(releaseInstallRoot);
                }

                // --- Try to extract Python path + working directory from .mcp.json ---
                foreach (var candidate in candidates)
                {
                    var mcpJsonPath = Path.Combine(candidate, ".mcp.json");
                    if (!File.Exists(mcpJsonPath))
                        continue;

                    try
                    {
                        var mcpJson = File.ReadAllText(mcpJsonPath);
                        using var doc = JsonDocument.Parse(mcpJson);
                        var servers = doc.RootElement.GetProperty("mcpServers");
                        if (servers.TryGetProperty("rook", out var rook))
                        {
                            if (rook.TryGetProperty("command", out var cmd))
                                pythonPath = cmd.GetString();
                            if (rook.TryGetProperty("cwd", out var cwd))
                                workingDirectory = cwd.GetString();
                        }
                    }
                    catch
                    {
                        continue;
                    }

                    if (!string.IsNullOrEmpty(pythonPath) && !string.IsNullOrEmpty(workingDirectory))
                        break;
                }

                // --- Find Python if .mcp.json didn't provide it ---
                if (string.IsNullOrEmpty(pythonPath) || !File.Exists(pythonPath))
                {
                    pythonPath = DiscoverManagedVenvPython();
                    if (string.IsNullOrEmpty(pythonPath) && AllowUserPythonDiscovery())
                    {
                        pythonPath = DiscoverPython();
                    }
                }

                if (string.IsNullOrEmpty(pythonPath) || !File.Exists(pythonPath))
                    return null;

                var releasePython = IsPrivateReleasePython(pythonPath);
                var releaseRoot = GetReleaseInstallRoot();
                if (releasePython && !string.IsNullOrEmpty(releaseRoot))
                {
                    workingDirectory = Path.Combine(releaseRoot, "mcp_server");
                }

                // --- Find working directory if .mcp.json didn't provide it ---
                if (string.IsNullOrEmpty(workingDirectory) || !Directory.Exists(workingDirectory))
                {
                    // Check candidate repo roots for mcp_server/
                    foreach (var candidate in candidates)
                    {
                        var mcpServerDir = Path.Combine(candidate, "mcp_server");
                        if (Directory.Exists(mcpServerDir))
                        {
                            workingDirectory = mcpServerDir;
                            break;
                        }
                    }
                }

                // --- If still no working directory, check if rook is pip-installed ---
                var pythonPathEntries = new List<string>();
                if (string.IsNullOrEmpty(workingDirectory) || !Directory.Exists(workingDirectory))
                {
                    var packageDir = ProbePipInstalledRook(pythonPath);
                    if (!string.IsNullOrEmpty(packageDir))
                    {
                        var editableProjectRoot = FindEditableProjectRoot(packageDir);
                        if (!string.IsNullOrEmpty(editableProjectRoot))
                        {
                            workingDirectory = editableProjectRoot;
                            AddSrcPathEntry(pythonPathEntries, workingDirectory);
                            RhinoApp.WriteLine(
                                $"Rook: detected editable install at {editableProjectRoot}, "
                                + "using as chat service working directory.");
                        }
                        else
                        {
                            // rook is importable via site-packages — use a temp
                            // working dir and no explicit PYTHONPATH entries.
                            workingDirectory = Path.GetTempPath();
                        }
                    }
                    else
                    {
                        RhinoApp.WriteLine(
                            "Rook: could not find mcp_server directory or pip-installed rook package. "
                            + "Set ROOK_PROJECT_ROOT or run: pip install -e <repo>/mcp_server");
                        return null;
                    }
                }
                else
                {
                    if (!releasePython)
                        AddSrcPathEntry(pythonPathEntries, workingDirectory);
                }

                var manifest = new ChatServiceManifest
                {
                    PythonPath = pythonPath,
                    WorkingDirectory = workingDirectory,
                    Module = "rook.agent.chat.service_main",
                    Owner = ExpectedOwner,
                    PythonPathEntries = pythonPathEntries,
                    Environment = releasePython
                        ? BuildReleaseManifestEnvironment()
                        : new Dictionary<string, string>(),
                };

                if (IsReleaseShapedManifest(manifest)
                    && !IsReleaseManifestContract(manifest, out var generatedReleaseReason))
                {
                    RhinoApp.WriteLine(
                        "Rook: generated release chat service manifest failed validation "
                        + $"({generatedReleaseReason}).");
                    return null;
                }

                // Persist the manifest so subsequent loads skip auto-generation.
                // If the plugin directory is read-only, return the in-memory
                // manifest so this session still works.
                try
                {
                    var json = JsonSerializer.Serialize(manifest, new JsonSerializerOptions
                    {
                        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                        WriteIndented = true,
                    });
                    var manifestDir = Path.GetDirectoryName(manifestPath);
                    if (!string.IsNullOrEmpty(manifestDir))
                        Directory.CreateDirectory(manifestDir);
                    File.WriteAllText(manifestPath, json);
                }
                catch (UnauthorizedAccessException)
                {
                    RhinoApp.WriteLine(
                        $"Rook: cannot write manifest to {manifestPath} (permission denied). "
                        + "Run register-rooknative-suite.ps1 or install to a writable location.");
                }
                catch (IOException ioEx)
                {
                    RhinoApp.WriteLine($"Rook: manifest write failed: {ioEx.Message}");
                }

                return manifest;
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"Rook: auto-generate manifest failed: {ex.Message}");
                return null;
            }
        }

        private static Dictionary<string, string> BuildReleaseManifestEnvironment()
        {
            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            var installRoot = Path.Combine(localAppData, "Rook", "app");
            var dataDir = Path.Combine(localAppData, "Rook", "data");
            return new Dictionary<string, string>
            {
                ["PYTHONPATH"] = "",
                ["PYTHONHOME"] = "",
                ["ROOK_INSTALL_ROOT"] = installRoot,
                ["ROOK_DATA_DIR"] = dataDir,
                ["ROOK_MODE"] = "release",
                ["DSPY_CACHEDIR"] = Path.Combine(dataDir, "dspy-cache"),
                ["ROOK_DSPY_RESTRICT_PICKLE"] = "1",
                ["CHIRP_HOME"] = Path.Combine(installRoot, "chirp"),
            };
        }

        private static string? GetReleaseInstallRoot()
        {
            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (string.IsNullOrWhiteSpace(localAppData))
                return null;

            return Path.Combine(localAppData, "Rook", "app");
        }

        private static string? DiscoverManagedVenvPython()
        {
            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (string.IsNullOrWhiteSpace(localAppData))
                return null;

            var candidate = Path.Combine(localAppData, "Rook", "venv", "Scripts", "python.exe");
            return File.Exists(candidate) ? candidate : null;
        }

        private static bool AllowUserPythonDiscovery()
        {
            var value = Environment.GetEnvironmentVariable("ROOK_ALLOW_USER_PYTHON_DISCOVERY");
            return string.Equals(value, "1", StringComparison.Ordinal)
                || string.Equals(value, "true", StringComparison.OrdinalIgnoreCase);
        }

        private static bool IsPrivateReleasePython(string pythonPath)
        {
            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (string.IsNullOrWhiteSpace(localAppData) || string.IsNullOrWhiteSpace(pythonPath))
                return false;

            var expected = Path.Combine(localAppData, "Rook", "venv", "Scripts", "python.exe");
            return PathsEqual(pythonPath, expected);
        }

        private static bool IsReleaseWorkingDirectory(string workingDirectory)
        {
            var releaseRoot = GetReleaseInstallRoot();
            if (string.IsNullOrWhiteSpace(releaseRoot) || string.IsNullOrWhiteSpace(workingDirectory))
                return false;

            try
            {
                var normalizedRoot = Path.GetFullPath(releaseRoot)
                    .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    + Path.DirectorySeparatorChar;
                var normalizedWorkingDirectory = Path.GetFullPath(workingDirectory)
                    .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    + Path.DirectorySeparatorChar;
                return normalizedWorkingDirectory.StartsWith(normalizedRoot, StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                return false;
            }
        }

        private static bool ManifestEnvironmentEquals(ChatServiceManifest manifest, string key, string expected)
        {
            return manifest.Environment != null
                && manifest.Environment.TryGetValue(key, out var value)
                && string.Equals(value ?? "", expected, StringComparison.OrdinalIgnoreCase);
        }

        private static string? ManifestEnvironmentValue(ChatServiceManifest manifest, string key)
        {
            return manifest.Environment != null && manifest.Environment.TryGetValue(key, out var value)
                ? value
                : null;
        }

        private static bool IsReleaseShapedManifest(ChatServiceManifest manifest)
        {
            return IsPrivateReleasePython(manifest.PythonPath)
                || IsReleaseWorkingDirectory(manifest.WorkingDirectory)
                || ManifestEnvironmentEquals(manifest, "ROOK_MODE", "release");
        }

        private static bool IsReleaseManifestContract(ChatServiceManifest manifest, out string reason)
        {
            if (!IsPrivateReleasePython(manifest.PythonPath))
            {
                reason = $"release manifest pythonPath must point to the private Rook venv: '{manifest.PythonPath}'";
                return false;
            }

            var releaseRoot = GetReleaseInstallRoot();
            var expectedWorkingDirectory = string.IsNullOrWhiteSpace(releaseRoot)
                ? ""
                : Path.Combine(releaseRoot, "mcp_server");
            if (string.IsNullOrWhiteSpace(expectedWorkingDirectory)
                || !PathsEqual(manifest.WorkingDirectory, expectedWorkingDirectory))
            {
                reason = $"release manifest workingDirectory must point to the installed mcp_server: '{manifest.WorkingDirectory}'";
                return false;
            }

            if (!string.Equals(manifest.Module, "rook.agent.chat.service_main", StringComparison.Ordinal))
            {
                reason = $"release manifest module must be rook.agent.chat.service_main: '{manifest.Module}'";
                return false;
            }

            if (manifest.PythonPathEntries != null
                && manifest.PythonPathEntries.Any(path => !string.IsNullOrWhiteSpace(path)))
            {
                reason = "release manifest must not set source pythonPathEntries";
                return false;
            }

            if (!ManifestEnvironmentEquals(manifest, "ROOK_MODE", "release"))
            {
                reason = "release manifest missing ROOK_MODE=release";
                return false;
            }

            if (!ManifestEnvironmentEquals(manifest, "ROOK_DSPY_RESTRICT_PICKLE", "1"))
            {
                reason = "release manifest missing ROOK_DSPY_RESTRICT_PICKLE=1";
                return false;
            }

            if (!ManifestEnvironmentEquals(manifest, "PYTHONPATH", ""))
            {
                reason = "release manifest must clear PYTHONPATH";
                return false;
            }

            if (!ManifestEnvironmentEquals(manifest, "PYTHONHOME", ""))
            {
                reason = "release manifest must clear PYTHONHOME";
                return false;
            }

            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            if (string.IsNullOrWhiteSpace(localAppData))
            {
                reason = "release manifest cannot be validated because LocalAppData is unavailable";
                return false;
            }

            var expectedInstallRoot = Path.Combine(localAppData, "Rook", "app");
            var installRoot = ManifestEnvironmentValue(manifest, "ROOK_INSTALL_ROOT") ?? "";
            if (!PathsEqual(installRoot, expectedInstallRoot))
            {
                reason = $"release manifest ROOK_INSTALL_ROOT must point to the installed Rook app root: '{installRoot}'";
                return false;
            }

            var expectedDataDir = Path.Combine(localAppData, "Rook", "data");
            var dataDir = ManifestEnvironmentValue(manifest, "ROOK_DATA_DIR") ?? "";
            if (!PathsEqual(dataDir, expectedDataDir))
            {
                reason = $"release manifest ROOK_DATA_DIR must point to the installed Rook data root: '{dataDir}'";
                return false;
            }

            var dspyCacheDir = ManifestEnvironmentValue(manifest, "DSPY_CACHEDIR") ?? "";
            var expectedDspyCacheDir = Path.Combine(expectedDataDir, "dspy-cache");
            if (!PathsEqual(dspyCacheDir, expectedDspyCacheDir))
            {
                reason = $"release manifest DSPY_CACHEDIR must point to the installed Rook data dspy-cache: '{dspyCacheDir}'";
                return false;
            }

            var chirpHome = ManifestEnvironmentValue(manifest, "CHIRP_HOME") ?? "";
            var expectedChirpHome = Path.Combine(expectedInstallRoot, "chirp");
            if (!PathsEqual(chirpHome, expectedChirpHome))
            {
                reason = $"release manifest CHIRP_HOME must point to the installed Rook app Chirp home: '{chirpHome}'";
                return false;
            }

            reason = "";
            return true;
        }

        private static bool AllowProjectRootEnvironment(ChatServiceManifest manifest)
        {
            return !IsReleaseShapedManifest(manifest) && AllowUserPythonDiscovery();
        }

        /// <summary>
        /// Returns true when the cached manifest still matches the current runtime
        /// contract. This is stricter than "paths exist": it also detects the
        /// upgrade case where an older build wrote %TEMP% as the working directory
        /// even though rook is currently importable from an editable checkout.
        /// </summary>
        private static bool IsManifestCurrent(ChatServiceManifest manifest, out string reason)
        {
            if (!File.Exists(manifest.PythonPath))
            {
                reason = $"python path missing: '{manifest.PythonPath}'";
                return false;
            }

            if (!Directory.Exists(manifest.WorkingDirectory))
            {
                reason = $"working directory missing: '{manifest.WorkingDirectory}'";
                return false;
            }

            if (IsReleaseShapedManifest(manifest))
            {
                return IsReleaseManifestContract(manifest, out reason);
            }

            if (Directory.Exists(Path.Combine(manifest.WorkingDirectory, "src")))
            {
                reason = "";
                return true;
            }

            var packageDir = ProbePipInstalledRook(manifest.PythonPath);
            if (string.IsNullOrEmpty(packageDir))
            {
                reason = "";
                return true;
            }

            var editableProjectRoot = FindEditableProjectRoot(packageDir);
            if (string.IsNullOrEmpty(editableProjectRoot))
            {
                reason = "";
                return true;
            }

            if (PathsEqual(manifest.WorkingDirectory, editableProjectRoot))
            {
                reason = "";
                return true;
            }

            reason =
                $"working directory '{manifest.WorkingDirectory}' does not match detected editable install root '{editableProjectRoot}'";
            return false;
        }

        /// <summary>
        /// Adds the standard "src" path entry when a working directory follows the
        /// expected Python project layout.
        /// </summary>
        private static void AddSrcPathEntry(List<string> pythonPathEntries, string workingDirectory)
        {
            var srcDir = Path.Combine(workingDirectory, "src");
            if (Directory.Exists(srcDir)
                && !pythonPathEntries.Contains(srcDir, StringComparer.OrdinalIgnoreCase))
            {
                pythonPathEntries.Add(srcDir);
            }
        }

        /// <summary>
        /// Walks upward from an imported rook package directory looking for the
        /// editable Python project root. We identify it by the presence of both
        /// pyproject.toml and src/rook at the same ancestor.
        /// </summary>
        private static string? FindEditableProjectRoot(string packageDir)
        {
            try
            {
                var dir = new DirectoryInfo(packageDir.Trim());
                for (int i = 0; i < 8 && dir != null; i++, dir = dir.Parent)
                {
                    if (File.Exists(Path.Combine(dir.FullName, "pyproject.toml"))
                        && Directory.Exists(Path.Combine(dir.FullName, "src", "rook")))
                    {
                        return dir.FullName;
                    }
                }
            }
            catch
            {
                // Fall through to null. The caller will treat this as a
                // non-editable install and use the existing fallback.
            }

            return null;
        }

        private static bool PathsEqual(string left, string right)
        {
            try
            {
                var normalizedLeft = Path.GetFullPath(left.Trim())
                    .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                var normalizedRight = Path.GetFullPath(right.Trim())
                    .TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
                return string.Equals(normalizedLeft, normalizedRight, StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                return string.Equals(left.Trim(), right.Trim(), StringComparison.OrdinalIgnoreCase);
            }
        }

        /// <summary>
        /// Runs a process and captures stdout with a hard timeout.
        /// Returns (exitCode, stdout) or (null, null) on failure/timeout.
        ///
        /// Uses async reads with a deadline to avoid two classic deadlocks:
        ///   1. ReadToEnd() blocking forever if the child hangs
        ///   2. Unread stderr filling the OS pipe buffer (4 KB), blocking the child
        /// </summary>
        private static (int? ExitCode, string? Output) RunProcessWithTimeout(
            string fileName, string arguments, int timeoutMs)
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = fileName,
                    Arguments = arguments,
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true,
                };
                using var proc = Process.Start(psi);
                if (proc == null) return (null, null);

                // Drain stderr asynchronously so it never fills the pipe buffer.
                proc.BeginErrorReadLine();

                // Read stdout with a timeout to prevent indefinite blocking.
                var readTask = proc.StandardOutput.ReadToEndAsync();
                if (!proc.WaitForExit(timeoutMs))
                {
                    try { proc.Kill(); } catch { }
                    return (null, null);
                }

                // Process exited within timeout — stdout should be available.
                // Give ReadToEndAsync a brief grace period to finish.
                if (!readTask.Wait(2000))
                    return (null, null);

                return (proc.ExitCode, readTask.Result.Trim());
            }
            catch
            {
                return (null, null);
            }
        }

        /// <summary>
        /// Discovers a Python interpreter by searching PATH, the Windows Python
        /// Launcher (py -3), and common install locations — in that order.
        /// Returns the absolute path to python.exe, or null.
        /// </summary>
        private static string? DiscoverPython()
        {
            // 1. Try PATH via `where python`
            var (exitCode, output) = RunProcessWithTimeout("where", "python", 5000);
            if (exitCode == 0 && !string.IsNullOrEmpty(output))
            {
                // `where` can return multiple lines — take the first real Python.
                // Skip the Windows Store stub (WindowsApps\python.exe) which is a
                // redirector that opens the Microsoft Store, not a real interpreter.
                var first = output.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
                    .FirstOrDefault(line =>
                        line.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
                        && line.IndexOf("WindowsApps", StringComparison.OrdinalIgnoreCase) < 0);
                if (first != null && File.Exists(first))
                    return first;
            }

            // 2. Try Windows Python Launcher (`py -3 -c "..."`)
            (exitCode, output) = RunProcessWithTimeout("py", "-3 -c \"import sys; print(sys.executable)\"", 5000);
            if (exitCode == 0 && !string.IsNullOrEmpty(output) && File.Exists(output))
                return output;

            // 3. Check common Windows install locations (Python 3.11-3.14)
            var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            for (int minor = 14; minor >= 11; minor--)
            {
                var candidate = Path.Combine(localAppData, "Programs", "Python", $"Python3{minor}", "python.exe");
                if (File.Exists(candidate))
                    return candidate;
            }

            return null;
        }

        /// <summary>
        /// Checks whether the rook package is importable by the given Python.
        /// Returns the package directory if found, null otherwise.
        /// </summary>
        private static string? ProbePipInstalledRook(string pythonPath)
        {
            var (exitCode, output) = RunProcessWithTimeout(
                pythonPath,
                "-c \"import rook.agent.chat.service_main; import rook; print(rook.__path__[0])\"",
                10000);
            if (exitCode == 0 && !string.IsNullOrEmpty(output))
                return output;
            return null;
        }

        private async Task<Uri?> ResolveHealthyBaseUriAsync(CancellationToken ct)
        {
            // Discovery files are the sole source of truth.
            // Use the explicit host from the discovery payload instead of
            // hardcoding "localhost" — avoids IPv4/IPv6 ambiguity on Windows.
            foreach (var entry in GetOwnedDiscoveryRecords())
            {
                try
                {
                    var host = string.IsNullOrWhiteSpace(entry.Record.Host) ? "127.0.0.1" : entry.Record.Host;
                    var candidate = new Uri($"http://{host}:{entry.Record.Port}");
                    if (await IsOwnedServiceHealthyAsync(candidate, ct))
                    {
                        return candidate;
                    }
                }
                catch
                {
                    // Ignore stale or malformed discovery files.
                }
            }

            return null;
        }

        private async Task<bool> IsServiceHealthyAsync(Uri baseUri, CancellationToken ct)
        {
            try
            {
                using var request = new HttpRequestMessage(HttpMethod.Get, new Uri(baseUri, "/agent/chat/health"));
                using var response = await _httpClient.SendAsync(request, ct);
                return response.IsSuccessStatusCode;
            }
            catch
            {
                return false;
            }
        }

        /// <summary>
        /// Health check that also verifies the service owner matches <see cref="ExpectedOwner"/>.
        /// This prevents the C# panel from latching onto a chat server started by the MCP process
        /// (owner="external") when the panel needs its own (owner="rhino-panel").
        /// </summary>
        private async Task<bool> IsOwnedServiceHealthyAsync(Uri baseUri, CancellationToken ct)
        {
            try
            {
                var health = await QueryHealthAsync(baseUri, ct);
                return health != null && health.ServiceAvailable;
            }
            catch
            {
                return false;
            }
        }

        private async Task<ChatServiceHealth?> QueryHealthAsync(Uri baseUri, CancellationToken ct)
        {
            try
            {
                using var response = await _httpClient.GetAsync(new Uri(baseUri, "/agent/chat/health"), ct);
                response.EnsureSuccessStatusCode();
                var json = await response.Content.ReadAsStringAsync();
                var payload = JsonSerializer.Deserialize<ChatServiceHealthEnvelope>(json, JsonOptions);
                if (payload?.Service == null)
                {
                    return null;
                }

                if (!string.Equals(payload.Service.Owner, ExpectedOwner, StringComparison.OrdinalIgnoreCase))
                {
                    return null;
                }

                if (payload.Service.RhinoProcessId != CurrentRhinoProcessId)
                {
                    return null;
                }

                var serviceOk = string.Equals(payload.Service.Status, "ok", StringComparison.OrdinalIgnoreCase)
                    || payload.Service.Ok;
                return new ChatServiceHealth
                {
                    ServiceAvailable = serviceOk,
                    ServiceMessage = serviceOk ? "Chat service available" : "Chat service unavailable",
                    BaseUri = baseUri,
                    RuntimeAvailable = payload.Runtime?.Available ?? false,
                    RhinoConnected = payload.Runtime?.Rhino?.Connected ?? false,
                    PromptAvailable = payload.Runtime?.Prompt?.Available ?? false,
                    PromptActive = payload.Runtime?.Prompt?.IsActive ?? false,
                    PromptText = payload.Runtime?.Prompt?.Prompt ?? "",
                    LlmConfigured = payload.Runtime?.Llm?.Configured ?? false,
                    LlmMessage = payload.Runtime?.Llm?.Message ?? "",
                };
            }
            catch
            {
                return null;
            }
        }

        private void StartProcess(ChatServiceManifest manifest)
        {
            var startDecision = ShouldStartChatService(
                trackedProcessExists: _ownedProcess != null,
                trackedProcessHasExited: _ownedProcess?.HasExited ?? true,
                existingServiceAvailable: false,
                sessionNoncePresent: !string.IsNullOrEmpty(SessionNonce));
            if (startDecision == ChatServiceStartDecision.WaitForTrackedProcess)
            {
                return;
            }

            // ── Handle-inheritance fix ──────────────────────────────────
            // .NET Framework 4.8's Process.Start() with UseShellExecute=false
            // always calls CreateProcess with bInheritHandles=TRUE.  Combined
            // with .NET Framework's inheritable FileStream handles, this causes
            // the Python subprocess to inherit Rhino's .3dm file handle.
            // _SaveSmall then fails ("temporary file could not be renamed")
            // because the Python process still holds the file open.
            //
            // Fix: UseShellExecute=true calls ShellExecuteEx, which does NOT
            // inherit handles.  Trade-off: no pipe-based stdout/stderr capture
            // (we tail a log file instead) and no ProcessStartInfo.Environment
            // (we set env vars temporarily in the parent process).

            // Generate a fresh session nonce for this chat-server lifetime.
            var nonceBytes = new byte[32];
            using (var rng = System.Security.Cryptography.RandomNumberGenerator.Create())
                rng.GetBytes(nonceBytes);
            SessionNonce = Convert.ToBase64String(nonceBytes);

            // Collect environment overrides.
            var envOverrides = new Dictionary<string, string>
            {
                ["PYTHONHOME"] = "",
                ["ROOK_CHAT_SERVICE_OWNER"] = manifest.Owner,
                [NonceEnvVar] = SessionNonce,
            };
            foreach (var kv in manifest.Environment)
            {
                if (!string.IsNullOrWhiteSpace(kv.Key))
                    envOverrides[kv.Key] = kv.Value ?? "";
            }
            envOverrides["PYTHONHOME"] = "";
            envOverrides["ROOK_CHAT_SERVICE_OWNER"] = manifest.Owner;
            envOverrides[NonceEnvVar] = SessionNonce;
            var pythonPathEntries = manifest.PythonPathEntries
                .Where(path => !string.IsNullOrWhiteSpace(path))
                .Where(Directory.Exists)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToList();
            if (pythonPathEntries.Count > 0)
                envOverrides["PYTHONPATH"] = string.Join(";", pythonPathEntries);
            foreach (var key in new[] { "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ROOK_LOG_LEVEL" })
            {
                var value = Environment.GetEnvironmentVariable(key);
                if (!string.IsNullOrEmpty(value))
                    envOverrides[key] = value;
            }
            if (AllowProjectRootEnvironment(manifest))
            {
                var projectRoot = Environment.GetEnvironmentVariable("ROOK_PROJECT_ROOT");
                if (!string.IsNullOrEmpty(projectRoot))
                    envOverrides["ROOK_PROJECT_ROOT"] = projectRoot;
            }

            // Set up log file for output capture.
            var logDir = Path.Combine(Path.GetTempPath(), "rook");
            Directory.CreateDirectory(logDir);
            var logFile = Path.Combine(logDir, "chat_service.log");
            // Truncate any stale log from a previous session.
            try { File.WriteAllText(logFile, ""); } catch { }
            envOverrides["ROOK_LOG_FILE"] = logFile;

            // Temporarily set env vars in the parent process.  We're on the
            // UI thread so no other UI-thread code sees the temporary state.
            var savedEnv = new Dictionary<string, string?>();
            foreach (var kv in envOverrides)
            {
                savedEnv[kv.Key] = Environment.GetEnvironmentVariable(kv.Key);
                Environment.SetEnvironmentVariable(kv.Key, kv.Value);
            }

            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = manifest.PythonPath,
                    Arguments = $"-m {manifest.Module} --port 0 --owner {manifest.Owner} --rhino-process-id {CurrentRhinoProcessId}",
                    WorkingDirectory = manifest.WorkingDirectory,
                    UseShellExecute = true,
                    WindowStyle = ProcessWindowStyle.Hidden,
                };

                var process = new Process
                {
                    StartInfo = psi,
                    EnableRaisingEvents = true,
                };

                process.Exited += (_, __) =>
                {
                    RhinoApp.WriteLine("[RookChatService] process exited");
                    StopLogTailer();
                };

                process.Start();
                _ownedProcess = process;

                // Start background log tailer to forward Python output
                // to Rhino's command line (replaces pipe-based capture).
                StartLogTailer(logFile);
            }
            finally
            {
                // Restore environment immediately.
                foreach (var kv in savedEnv)
                {
                    Environment.SetEnvironmentVariable(kv.Key, kv.Value);
                }
            }
        }

        private void StartLogTailer(string logFile)
        {
            StopLogTailer();
            _logTailerCts = new CancellationTokenSource();
            var ct = _logTailerCts.Token;

            Task.Run(async () =>
            {
                // Wait briefly for the file to be created by Python.
                await Task.Delay(500, ct).ConfigureAwait(false);

                try
                {
                    using (var stream = new FileStream(logFile, FileMode.OpenOrCreate,
                        FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
                    using (var reader = new StreamReader(stream))
                    {
                        while (!ct.IsCancellationRequested)
                        {
                            var line = await reader.ReadLineAsync().ConfigureAwait(false);
                            if (line != null)
                            {
                                if (!string.IsNullOrWhiteSpace(line))
                                {
                                    RhinoApp.WriteLine($"[RookChatService:stderr] {line}");
                                }
                            }
                            else
                            {
                                // No more data — poll every 500ms.
                                await Task.Delay(500, ct).ConfigureAwait(false);
                            }
                        }
                    }
                }
                catch (OperationCanceledException) { }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"[RookChatService] log tailer error: {ex.Message}");
                }
            }, ct);
        }

        private void StopLogTailer()
        {
            _logTailerCts?.Cancel();
            _logTailerCts?.Dispose();
            _logTailerCts = null;
        }

        private async Task<ChatServiceHealth?> WaitForHealthyServiceAsync(CancellationToken ct)
        {
            var deadline = DateTime.UtcNow.Add(StartupTimeout);
            while (DateTime.UtcNow < deadline && !ct.IsCancellationRequested)
            {
                if (_ownedProcess != null && _ownedProcess.HasExited)
                {
                    return new ChatServiceHealth
                    {
                        ServiceAvailable = false,
                        ServiceMessage = "Chat service exited during startup. Check the Rhino command history for [RookChatService:stderr] details.",
                    };
                }

                var baseUri = await ResolveHealthyBaseUriAsync(ct);
                if (baseUri != null)
                {
                    var health = await QueryHealthAsync(baseUri, ct);
                    if (health != null && health.ServiceAvailable)
                    {
                        return health;
                    }
                }

                await Task.Delay(StartupPollInterval, ct);
            }

            return null;
        }

        private void StopOwnedProcess()
        {
            StopLogTailer();

            if (_ownedProcess == null)
            {
                return;
            }

            try
            {
                if (!_ownedProcess.HasExited)
                {
                    _ownedProcess.Kill();
                    _ownedProcess.WaitForExit(5000);
                }
            }
            catch
            {
                // Best-effort shutdown.
            }
            finally
            {
                _ownedProcess.Dispose();
                _ownedProcess = null;
            }
        }

        private void StopServicesBestEffort()
        {
            StopOwnedProcess();
            StopDiscoveredOwnedService();
        }

        private void StopDiscoveredOwnedService()
        {
            foreach (var entry in GetOwnedDiscoveryRecords())
            {
                try
                {
                    if (_ownedProcess != null && !_ownedProcess.HasExited && _ownedProcess.Id == entry.Record.Pid)
                    {
                        continue;
                    }

                    var process = Process.GetProcessById(entry.Record.Pid);
                    process.Kill();
                    process.WaitForExit(5000);
                }
                catch
                {
                    // Best-effort shutdown of previously discovered owned services.
                }

                try
                {
                    File.Delete(entry.Path);
                }
                catch
                {
                    // Best-effort cleanup of stale discovery files.
                }
            }
        }

        /// <summary>
        /// Removes chat-service-*.json files whose owning process is no longer
        /// alive.  Called before attempting to resolve or start a service so that
        /// stale files from crashed sessions don't cause phantom connections.
        /// </summary>
        private static void CleanupStaleChatDiscoveryFiles()
        {
            try
            {
                var folder = GetDiscoveryFolder();
                if (!Directory.Exists(folder))
                    return;

                foreach (var file in Directory.GetFiles(folder, "chat-service-*.json"))
                {
                    try
                    {
                        var json = File.ReadAllText(file);
                        var record = JsonSerializer.Deserialize<ChatServiceDiscoveryRecord>(json, JsonOptions);
                        if (record == null || record.Pid <= 0)
                        {
                            File.Delete(file);
                            continue;
                        }

                        try
                        {
                            Process.GetProcessById(record.Pid);
                            // Process is alive — leave the file.
                        }
                        catch (Exception) when (true)
                        {
                            // ArgumentException = PID not found (dead).
                            // InvalidOperationException = insufficient permissions.
                            // Either way, treat as stale — remove the file.
                            File.Delete(file);
                            RhinoApp.WriteLine($"Rook: cleaned stale chat discovery file {Path.GetFileName(file)} (PID {record.Pid} dead)");
                        }
                    }
                    catch
                    {
                        // Malformed file — remove it.
                        try { File.Delete(file); } catch { }
                    }
                }
            }
            catch
            {
                // Best-effort cleanup — don't block startup.
            }
        }
    }
}
