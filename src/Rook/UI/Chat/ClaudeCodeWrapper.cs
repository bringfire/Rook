using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using Rhino;

namespace Rook.UI.Chat
{
    /// <summary>
    /// Wraps the Claude Code CLI as a persistent subprocess using stream-json I/O.
    /// The process is launched once and stays alive; user messages are written to stdin
    /// as JSON objects and responses arrive on stdout via StreamJsonParser.
    /// </summary>
    public class ClaudeCodeWrapper : IDisposable
    {
        // ─── Events for UI updates ─────────────────────────────────────────
        public event Action<string>? OnStreamingUpdate;
        public event Action? OnMessageComplete;
        public event Action<string>? OnError;
        public event Action<string, string>? OnToolExecuted;
        public event Action<string>? OnWorkingDirectoryChanged;
        public event Action? OnReady;
        public event Action<string>? OnProcessDied;

        // ─── Internal state ────────────────────────────────────────────────
        private Process? _currentProcess;
        private readonly StringBuilder _streamingContent;
        private readonly StreamJsonParser _parser;
        private readonly StringBuilder _stderrBuffer;
        private readonly object _processLock = new object();
        private bool _disposed;
        private bool _ready;

        // ─── Configuration ─────────────────────────────────────────────────
        private string? _customWorkingDirectory;
        private string? _panelMcpConfigPath;
        private readonly uint _documentSerialNumber;

        /// <summary>
        /// Whether the persistent Claude Code process is running.
        /// </summary>
        public bool IsRunning
        {
            get
            {
                lock (_processLock)
                {
                    return _currentProcess != null && !_currentProcess.HasExited;
                }
            }
        }

        /// <summary>
        /// Gets the current working directory that Claude Code will use.
        /// </summary>
        public string WorkingDirectory => GetWorkingDirectory();

        /// <summary>
        /// Sets a custom working directory. Set to null to use automatic detection.
        /// </summary>
        public void SetWorkingDirectory(string? path)
        {
            if (path != null && !Directory.Exists(path))
            {
                throw new DirectoryNotFoundException($"Directory not found: {path}");
            }
            _customWorkingDirectory = path;
            OnWorkingDirectoryChanged?.Invoke(GetWorkingDirectory());
        }

        public ClaudeCodeWrapper(uint documentSerialNumber = 0)
        {
            _documentSerialNumber = documentSerialNumber;
            _streamingContent = new StringBuilder();
            _stderrBuffer = new StringBuilder();
            _parser = new StreamJsonParser();

            // Wire up parser events
            _parser.OnTextDelta += HandleTextDelta;
            _parser.OnToolStart += HandleToolStart;
            _parser.OnToolComplete += HandleToolComplete;
            _parser.OnSessionId += HandleSessionId;
            _parser.OnError += HandleParserError;
            _parser.OnMessageComplete += HandleMessageComplete;
        }

        // ─── Working directory ─────────────────────────────────────────────

        /// <summary>
        /// Gets the working directory for Claude Code CLI.
        /// Priority: Custom override > Rhino document folder > User Documents
        /// </summary>
        private string GetWorkingDirectory()
        {
            // 1. Custom override takes priority
            if (!string.IsNullOrEmpty(_customWorkingDirectory) && Directory.Exists(_customWorkingDirectory))
            {
                return _customWorkingDirectory;
            }

            // 2. Try to use the Rhino document's folder
            try
            {
                var doc = RhinoDoc.ActiveDoc;
                if (doc != null && !string.IsNullOrEmpty(doc.Path))
                {
                    var docFolder = Path.GetDirectoryName(doc.Path);
                    if (!string.IsNullOrEmpty(docFolder) && Directory.Exists(docFolder))
                    {
                        return docFolder;
                    }
                }
            }
            catch
            {
                // Ignore errors accessing RhinoDoc
            }

            // 3. Fall back to user's Documents folder
            var documentsPath = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
            if (Directory.Exists(documentsPath))
            {
                return documentsPath;
            }

            // 4. Last resort: current directory
            return Environment.CurrentDirectory;
        }

        // ─── Persistent process lifecycle ──────────────────────────────────

        /// <summary>
        /// Launch the persistent Claude Code subprocess. The process stays alive
        /// and accepts user messages on stdin as stream-json objects.
        /// </summary>
        public void StartPersistentProcess()
        {
            lock (_processLock)
            {
                if (_currentProcess != null && !_currentProcess.HasExited)
                {
                    RhinoApp.WriteLine("[ClaudeCodeWrapper] Process already running");
                    return;
                }

                // Verify claude CLI is available before launching
                if (!IsClaudeCliAvailable())
                {
                    OnError?.Invoke("Claude Code CLI not found. Please install it with: npm install -g @anthropic-ai/claude-code");
                    return;
                }

                _ready = false;
                _stderrBuffer.Clear();
                _parser.Reset();
                _streamingContent.Clear();

                string args;
                try
                {
                    args = BuildLaunchArguments();
                }
                catch (InvalidOperationException ex)
                {
                    OnError?.Invoke(ex.Message);
                    RhinoApp.WriteLine($"[ClaudeCodeWrapper] {ex}");
                    return;
                }

                var workDir = GetWorkingDirectory();

                RhinoApp.WriteLine($"[ClaudeCodeWrapper] Starting persistent process: claude {args}");
                RhinoApp.WriteLine($"[ClaudeCodeWrapper] Working directory: {workDir}");

                var psi = new ProcessStartInfo
                {
                    FileName = "claude",
                    Arguments = args,
                    WorkingDirectory = workDir,
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    RedirectStandardInput = true,
                    CreateNoWindow = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8
                };

                _currentProcess = new Process { StartInfo = psi, EnableRaisingEvents = true };

                // Wire up event-based output reading
                _currentProcess.OutputDataReceived += OnOutputDataReceived;
                _currentProcess.ErrorDataReceived += OnErrorDataReceived;
                _currentProcess.Exited += OnProcessExited;

                _currentProcess.Start();
                _currentProcess.BeginOutputReadLine();
                _currentProcess.BeginErrorReadLine();

                RhinoApp.WriteLine("[ClaudeCodeWrapper] Persistent process started");
            }
        }

        /// <summary>
        /// Write a user message to the persistent process's stdin as stream-json.
        /// </summary>
        public void WriteMessage(string message)
        {
            if (string.IsNullOrWhiteSpace(message))
            {
                OnError?.Invoke("Empty message");
                return;
            }

            lock (_processLock)
            {
                if (_currentProcess == null || _currentProcess.HasExited)
                {
                    OnError?.Invoke("Process is not running. Call StartPersistentProcess() first.");
                    return;
                }

                try
                {
                    _streamingContent.Clear();
                    _parser.Reset();

                    // Build the stream-json user message
                    // Claude Code expects: {"type":"user","message":{"role":"user","content":[{"type":"text","text":"..."}]}}
                    var jsonMessage = JsonSerializer.Serialize(new
                    {
                        type = "user",
                        message = new
                        {
                            role = "user",
                            content = new[]
                            {
                                new { type = "text", text = message }
                            }
                        }
                    });

                    _currentProcess.StandardInput.WriteLine(jsonMessage);
                    _currentProcess.StandardInput.Flush();

                    RhinoApp.WriteLine($"[ClaudeCodeWrapper] Sent message ({message.Length} chars)");
                }
                catch (Exception ex)
                {
                    OnError?.Invoke($"Failed to write message: {ex.Message}");
                }
            }
        }

        /// <summary>
        /// Kill the current process and restart it.
        /// </summary>
        public void Reconnect()
        {
            RhinoApp.WriteLine("[ClaudeCodeWrapper] Reconnecting...");
            KillProcess();
            StartPersistentProcess();
        }

        /// <summary>
        /// Cancel the current request by killing and restarting the process.
        /// Claude Code CLI does not support in-band cancellation, so a process
        /// restart is the only reliable way to stop a running turn.
        /// </summary>
        public void CancelCurrentRequest()
        {
            RhinoApp.WriteLine("[ClaudeCodeWrapper] Cancel requested — restarting process");
            KillProcess();
            StartPersistentProcess();
        }

        /// <summary>
        /// Clear conversation state. Restarts the process to get a fresh session.
        /// </summary>
        public void ClearConversation()
        {
            _streamingContent.Clear();
            _parser.Reset();
            Reconnect();
        }

        // ─── Process output handlers ───────────────────────────────────────

        private void OnOutputDataReceived(object sender, DataReceivedEventArgs e)
        {
            if (e.Data != null)
            {
                // Detect readiness from first system event
                if (!_ready && e.Data.Contains("\"type\":\"system\""))
                {
                    _ready = true;
                    OnReady?.Invoke();
                }

                _parser.ParseLine(e.Data);
            }
        }

        private void OnErrorDataReceived(object sender, DataReceivedEventArgs e)
        {
            if (e.Data != null)
            {
                _stderrBuffer.AppendLine(e.Data);
                RhinoApp.WriteLine($"[ClaudeCodeWrapper] stderr: {e.Data}");

                // Surface critical errors
                if (e.Data.Contains("Error:") || e.Data.Contains("FATAL"))
                {
                    OnError?.Invoke(e.Data);
                }
            }
        }

        private void OnProcessExited(object? sender, EventArgs e)
        {
            int exitCode = -1;
            lock (_processLock)
            {
                if (_currentProcess != null)
                {
                    try
                    {
                        exitCode = _currentProcess.ExitCode;
                    }
                    catch
                    {
                        // Process may already be disposed
                    }
                }
            }

            var reason = $"Exit code {exitCode}";
            var stderr = _stderrBuffer.ToString().Trim();
            if (!string.IsNullOrEmpty(stderr))
            {
                // Include the last line of stderr for context
                var lines = stderr.Split('\n');
                var lastLine = lines[lines.Length - 1].Trim();
                if (!string.IsNullOrEmpty(lastLine))
                {
                    reason += $" - {lastLine}";
                }
            }

            RhinoApp.WriteLine($"[ClaudeCodeWrapper] Process died: {reason}");
            OnProcessDied?.Invoke(reason);
        }

        // ─── Parser event handlers ─────────────────────────────────────────

        private void HandleTextDelta(string text)
        {
            _streamingContent.Append(text);
            OnStreamingUpdate?.Invoke(_streamingContent.ToString());
        }

        private void HandleToolStart(string toolName)
        {
            _streamingContent.AppendLine();
            _streamingContent.Append($"[tool] {toolName}...");
            OnStreamingUpdate?.Invoke(_streamingContent.ToString());
        }

        private void HandleToolComplete(string toolName, string result)
        {
            // Replace the "..." with "completed"
            var content = _streamingContent.ToString();
            var searchFor = $"[tool] {toolName}...";
            var replaceWith = $"[done] {toolName}";

            if (content.EndsWith(searchFor))
            {
                _streamingContent.Length -= searchFor.Length;
                _streamingContent.Append(replaceWith);
            }

            OnStreamingUpdate?.Invoke(_streamingContent.ToString());
            OnToolExecuted?.Invoke(toolName, result);
        }

        private void HandleSessionId(string sessionId)
        {
            RhinoApp.WriteLine($"[ClaudeCodeWrapper] Session ID: {sessionId}");
        }

        private void HandleParserError(string error)
        {
            RhinoApp.WriteLine($"[ClaudeCodeWrapper] Parser error: {error}");
        }

        private void HandleMessageComplete()
        {
            OnMessageComplete?.Invoke();
        }

        // ─── CLI availability check ────────────────────────────────────────

        /// <summary>
        /// Check if claude CLI is available in PATH. Called once at startup.
        /// </summary>
        private bool IsClaudeCliAvailable()
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "claude",
                    Arguments = "--version",
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true
                };

                using var process = Process.Start(psi);
                if (process == null) return false;

                process.WaitForExit(5000);
                return process.ExitCode == 0;
            }
            catch
            {
                return false;
            }
        }

        // ─── Launch arguments ──────────────────────────────────────────────

        /// <summary>
        /// Build the fixed launch arguments for the persistent process.
        /// </summary>
        private string BuildLaunchArguments()
        {
            var sb = new StringBuilder();

            // Stream-json for both input and output
            sb.Append("--input-format stream-json ");
            sb.Append("--output-format stream-json ");
            sb.Append("--verbose ");

            // Skip all permission checks (required for non-interactive use)
            sb.Append("--dangerously-skip-permissions ");

            // Create a strict, panel-locked MCP config containing only Rook.
            var userMcpConfig = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                ".claude.json");
            try
            {
                DeletePanelMcpConfig();
                _panelMcpConfigPath = ClaudePanelMcpConfigBuilder.WriteTempConfig(
                    userMcpConfig,
                    Process.GetCurrentProcess().Id,
                    _documentSerialNumber);
                sb.Append($"--mcp-config \"{_panelMcpConfigPath}\" ");
                sb.Append("--strict-mcp-config ");
            }
            catch (Exception ex)
            {
                throw new InvalidOperationException(
                    "Unable to create panel-locked Rook MCP config for Claude Code. Run Rook doctor to configure the rook MCP server for Claude Code.",
                    ex);
            }

            var prompt = "You are a Rhino 3D assistant running inside the Rook Rhino panel. "
                + "You only have access to the panel-locked Rook MCP server. "
                + "Use knowledge_query before operations to learn patterns. "
                + "Use knowledge_record after operations to record outcomes. "
                + "Do not claim access to Engram, Unreal Engine, Blueprints, or Engram knowledge "
                + "unless the user explicitly asks about those systems and a Rook tool result confirms that capability.";

            var docContext = _documentSerialNumber != 0
                ? $" The panel lock enforces documentSerialNumber {_documentSerialNumber}; do not target another Rhino document."
                : "";
            sb.Append($"--append-system-prompt \"{EscapeForCommandLine(prompt + docContext)}\" ");

            return sb.ToString().Trim();
        }

        /// <summary>
        /// Escape a string for safe use in command line arguments.
        /// </summary>
        private string EscapeForCommandLine(string input)
        {
            if (string.IsNullOrEmpty(input)) return "";

            return input
                .Replace("\\", "\\\\")
                .Replace("\"", "\\\"")
                .Replace("\r", "")
                .Replace("\n", " ");
        }

        // ─── Process management ────────────────────────────────────────────

        private void DeletePanelMcpConfig()
        {
            var path = _panelMcpConfigPath;
            _panelMcpConfigPath = null;
            if (string.IsNullOrWhiteSpace(path))
                return;

            try
            {
                if (File.Exists(path))
                    File.Delete(path);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"[ClaudeCodeWrapper] Failed to delete panel MCP config: {ex.Message}");
            }
        }

        /// <summary>
        /// Kill the current process if running.
        /// </summary>
        private void KillProcess()
        {
            lock (_processLock)
            {
                if (_currentProcess != null)
                {
                    try
                    {
                        // Unhook events before killing to avoid re-entrant OnProcessExited
                        _currentProcess.OutputDataReceived -= OnOutputDataReceived;
                        _currentProcess.ErrorDataReceived -= OnErrorDataReceived;
                        _currentProcess.Exited -= OnProcessExited;

                        if (!_currentProcess.HasExited)
                        {
                            // Try graceful close via stdin first
                            try
                            {
                                _currentProcess.StandardInput.Close();
                            }
                            catch { }

                            // Give it a moment, then force kill
                            if (!_currentProcess.WaitForExit(2000))
                            {
                                _currentProcess.Kill();
                            }
                        }

                        _currentProcess.Dispose();
                    }
                    catch (Exception ex)
                    {
                        RhinoApp.WriteLine($"[ClaudeCodeWrapper] Error killing process: {ex.Message}");
                    }
                    finally
                    {
                        _currentProcess = null;
                        _ready = false;
                        DeletePanelMcpConfig();
                    }
                }
                else
                {
                    DeletePanelMcpConfig();
                }
            }
        }

        // ─── IDisposable ───────────────────────────────────────────────────

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;

            _parser.OnTextDelta -= HandleTextDelta;
            _parser.OnToolStart -= HandleToolStart;
            _parser.OnToolComplete -= HandleToolComplete;
            _parser.OnSessionId -= HandleSessionId;
            _parser.OnError -= HandleParserError;
            _parser.OnMessageComplete -= HandleMessageComplete;

            KillProcess();
            DeletePanelMcpConfig();
        }
    }
}
