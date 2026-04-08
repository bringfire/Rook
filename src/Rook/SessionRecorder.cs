using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using Rhino;
using Rhino.Commands;
using Rhino.DocObjects;
using Rhino.Geometry;
using Rook.Models;

namespace Rook
{
    /// <summary>
    /// Event args for when a command is recorded.
    /// </summary>
    public class CommandRecordedEventArgs : EventArgs
    {
        public CommandRecord Record { get; set; } = new();
    }

    /// <summary>
    /// Event args for session lifecycle events.
    /// </summary>
    public class SessionEventArgs : EventArgs
    {
        public SessionData Session { get; set; } = new();
    }

    /// <summary>
    /// Records all commands (MCP + user) for session history.
    /// Persists sessions to %APPDATA%/Rook/sessions/.
    /// </summary>
    public class SessionRecorder
    {
        private static readonly Lazy<SessionRecorder> _instance = new(() => new SessionRecorder());
        public static SessionRecorder Instance => _instance.Value;

        private SessionData? _currentSession;
        private readonly object _lock = new();
        private string? _currentSessionFilePath;
        private int _sequenceNumber;
        private HashSet<Guid> _objectsBefore = new();
        private List<Guid> _selectionBefore = new();
        private List<SubObjectSelection> _subObjectSelectionBefore = new();
        private List<SubObjectSelection> _transformingSubObjects = new();
        private Transform? _capturedTransform;
        private Dictionary<string, Plane> _subObjectPlanesBefore = new();
        private CommandRecord? _pendingUserCommand;
        private Stopwatch? _commandStopwatch;
        private bool _isInitialized;
        private string? _initialPrompt;
        private bool _wasCapturingBefore;

        // Track if we're currently executing an MCP request (to distinguish from user commands)
        // volatile: written on background HTTP thread, read on main thread in OnCommandBegin/OnCommandEnd
        private volatile bool _isMcpRequest;

        /// <summary>
        /// Whether recording is active.
        /// </summary>
        public bool IsRecording => _currentSession != null;

        /// <summary>
        /// The current session data.
        /// </summary>
        public SessionData? CurrentSession => _currentSession;

        // Events
        public event EventHandler<CommandRecordedEventArgs>? CommandRecorded;
        public event EventHandler<SessionEventArgs>? SessionStarted;
        public event EventHandler<SessionEventArgs>? SessionEnded;

        private SessionRecorder() { }

        /// <summary>
        /// Initialize the session recorder and subscribe to events.
        /// </summary>
        public void Initialize()
        {
            if (_isInitialized) return;

            try
            {
                // Ensure base folder exists
                SessionPaths.EnsureBaseFolder();

                // Subscribe to Rhino command events
                Command.BeginCommand += OnCommandBegin;
                Command.EndCommand += OnCommandEnd;

                // Subscribe to transform events (for Gumball sub-object capture)
                RhinoDoc.BeforeTransformObjects += OnBeforeTransformObjects;

                // Subscribe to document events
                RhinoDoc.EndOpenDocument += OnDocumentOpened;
                RhinoDoc.CloseDocument += OnDocumentClosing;

                _isInitialized = true;
                RhinoApp.WriteLine("SessionRecorder: Initialized");

                // Start session for current document if one is open
                var doc = RhinoDoc.ActiveDoc;
                if (doc != null)
                {
                    StartSession(doc);
                }
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"SessionRecorder: Failed to initialize - {ex.Message}");
            }
        }

        /// <summary>
        /// Shutdown the session recorder and unsubscribe from events.
        /// </summary>
        public void Shutdown()
        {
            if (!_isInitialized) return;

            try
            {
                // End current session
                EndSession("shutdown");

                // Unsubscribe from events
                Command.BeginCommand -= OnCommandBegin;
                Command.EndCommand -= OnCommandEnd;
                RhinoDoc.BeforeTransformObjects -= OnBeforeTransformObjects;
                RhinoDoc.EndOpenDocument -= OnDocumentOpened;
                RhinoDoc.CloseDocument -= OnDocumentClosing;

                _isInitialized = false;
                RhinoApp.WriteLine("SessionRecorder: Shutdown complete");
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"SessionRecorder: Error during shutdown - {ex.Message}");
            }
        }

        /// <summary>
        /// Start a new recording session for a document.
        /// </summary>
        public void StartSession(RhinoDoc doc)
        {
            lock (_lock)
            {
                // End any existing session
                if (_currentSession != null)
                {
                    EndSessionInternal("new_document");
                }

                try
                {
                    _currentSession = new SessionData
                    {
                        StartedAt = DateTime.UtcNow,
                        Document = new DocumentInfo
                        {
                            Name = doc.Name ?? "Untitled",
                            Path = doc.Path ?? "",
                            Units = doc.ModelUnitSystem.ToString(),
                            ProjectFolder = SessionPaths.ExtractProjectFolder(doc.Path ?? "")
                        }
                    };

                    // Capture git info
                    CaptureGitInfo(_currentSession, doc.Path);

                    // Ensure folder exists and get file path
                    SessionPaths.EnsureSessionFolder(_currentSession.Document);
                    _currentSessionFilePath = SessionPaths.GetSessionFilePath(
                        _currentSession.Document,
                        _currentSession.StartedAt
                    );

                    _sequenceNumber = 0;

                    // Save initial session file
                    SaveSession();

                    RhinoApp.WriteLine($"SessionRecorder: Started session {_currentSession.Id} for {_currentSession.Document.Name}");

                    SessionStarted?.Invoke(this, new SessionEventArgs { Session = _currentSession });
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"SessionRecorder: Failed to start session - {ex.Message}");
                    _currentSession = null;
                }
            }
        }

        /// <summary>
        /// End the current recording session.
        /// </summary>
        public void EndSession(string reason = "normal")
        {
            lock (_lock)
            {
                EndSessionInternal(reason);
            }
        }

        private void EndSessionInternal(string reason)
        {
            if (_currentSession == null) return;

            try
            {
                _currentSession.EndedAt = DateTime.UtcNow;
                _currentSession.EndReason = reason;

                // Update stats
                UpdateStats();

                // Save final session
                SaveSession();

                RhinoApp.WriteLine($"SessionRecorder: Ended session {_currentSession.Id} ({reason}), {_currentSession.Commands.Count} commands recorded");

                var session = _currentSession;
                _currentSession = null;
                _currentSessionFilePath = null;

                SessionEnded?.Invoke(this, new SessionEventArgs { Session = session });
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"SessionRecorder: Error ending session - {ex.Message}");
            }
        }

        /// <summary>
        /// Record an MCP request (called from RookServer).
        /// </summary>
        public void RecordMcpRequest(string endpoint, string method, string? requestBody, ApiResponse response, double durationMs)
        {
            if (_currentSession == null) return;

            lock (_lock)
            {
                try
                {
                    _sequenceNumber++;
                    var record = new CommandRecord
                    {
                        Id = $"cmd_{_sequenceNumber:D4}",
                        SequenceNumber = _sequenceNumber,
                        Timestamp = DateTime.UtcNow,
                        Source = CommandSource.Mcp,
                        CommandName = ExtractCommandName(endpoint),
                        Endpoint = endpoint,
                        RawInput = requestBody,
                        Success = response.Success,
                        Response = response.Data,
                        DurationMs = durationMs
                    };

                    // Try to parse parameters from request body
                    if (!string.IsNullOrEmpty(requestBody))
                    {
                        try
                        {
                            record.Parameters = JsonSerializer.Deserialize<Dictionary<string, object>>(requestBody);
                        }
                        catch
                        {
                            // Ignore parse errors
                        }
                    }

                    // Extract error message if failed
                    if (!response.Success && response.Data is string errorMsg)
                    {
                        record.ErrorMessage = errorMsg;
                    }

                    // Try to extract created object IDs from response
                    if (response.Success && response.Data != null)
                    {
                        ExtractCreatedObjectIds(record, response.Data);

                        // NOTE: Do NOT call ExtractGeometryParameters here.
                        // RecordMcpRequest runs on a background HTTP thread —
                        // accessing RhinoDoc.ActiveDoc / doc.Objects from a background
                        // thread races with Rhino's file-save serialization and causes
                        // "_SaveSmall: temporary file could not be renamed" failures.
                    }

                    _currentSession.Commands.Add(record);

                    // Auto-save periodically (every 10 commands)
                    if (_currentSession.Commands.Count % 10 == 0)
                    {
                        SaveSession();
                    }

                    CommandRecorded?.Invoke(this, new CommandRecordedEventArgs { Record = record });
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"SessionRecorder: Error recording MCP request - {ex.Message}");
                }
            }
        }

        /// <summary>
        /// Record an AIGumball command with full drag history.
        /// Called directly by AIGumballCommand instead of going through the event-based
        /// OnCommandBegin/OnCommandEnd path, because the AIGumball command needs to record
        /// each drag operation as a GumballDragRecord — data that the event system can't capture.
        /// </summary>
        public void RecordAIGumballCommand(CommandRecord record)
        {
            if (_currentSession == null) return;

            lock (_lock)
            {
                try
                {
                    _sequenceNumber++;
                    record.Id = $"cmd_{_sequenceNumber:D4}";
                    record.SequenceNumber = _sequenceNumber;

                    _currentSession.Commands.Add(record);

                    // Auto-save periodically
                    if (_currentSession.Commands.Count % 10 == 0)
                    {
                        SaveSession();
                    }

                    CommandRecorded?.Invoke(this, new CommandRecordedEventArgs { Record = record });

                    RhinoApp.WriteLine($"SessionRecorder: Recorded AIGumball command with {record.GumballDragCount} drags");
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"SessionRecorder: Error recording AIGumball command - {ex.Message}");
                }
            }
        }

        /// <summary>
        /// Mark that an MCP request is starting (so user commands during this time are attributed correctly).
        /// </summary>
        public void BeginMcpRequest()
        {
            _isMcpRequest = true;
        }

        /// <summary>
        /// Mark that an MCP request has ended.
        /// </summary>
        public void EndMcpRequest()
        {
            _isMcpRequest = false;
        }

        // ==================== Rhino Event Handlers ====================

        private void OnCommandBegin(object sender, CommandEventArgs e)
        {
            if (_currentSession == null) return;

            // Skip if this is triggered by an MCP request (we record those separately)
            if (_isMcpRequest) return;

            // Skip AIGumball and AIGumballDrag — they record via RecordAIGumballCommand()
            // Must skip here too, not just OnCommandEnd, to avoid dangling state
            // (CommandWindowCaptureEnabled, _pendingUserCommand, _objectsBefore, etc.)
            var cmdNameCheck = e.CommandEnglishName?.ToLower() ?? "";
            if (cmdNameCheck == "aigumball" || cmdNameCheck == "aigumballdrag") return;

            // Skip save commands — enumerating doc.Objects during save interferes
            // with Rhino's serialization and causes "temporary file could not be renamed"
            if (cmdNameCheck == "save" || cmdNameCheck == "savesmall" ||
                cmdNameCheck == "saveas" || cmdNameCheck == "savesmallas" ||
                cmdNameCheck == "incrementalsave") return;

            try
            {
                var doc = RhinoDoc.ActiveDoc;
                if (doc == null) return;

                // Snapshot objects before command
                _objectsBefore = new HashSet<Guid>(doc.Objects.Select(o => o.Id));

                // Capture selection before command (these are the input objects)
                _selectionBefore = new List<Guid>();
                _subObjectSelectionBefore = new List<SubObjectSelection>();
                foreach (var obj in doc.Objects.GetSelectedObjects(includeLights: false, includeGrips: false))
                {
                    _selectionBefore.Add(obj.Id);
                }

                // Capture sub-object selections (edges, faces, vertices)
                // Must check ALL objects, not just selected ones - sub-object selection
                // doesn't always mean the parent object is in GetSelectedObjects()
                _subObjectPlanesBefore.Clear();
                foreach (var obj in doc.Objects)
                {
                    var selectedSubObjects = obj.GetSelectedSubObjects();
                    if (selectedSubObjects != null && selectedSubObjects.Length > 0)
                    {
                        // Get the Brep geometry for plane capture
                        var brep = obj.Geometry as Brep;

                        foreach (var ci in selectedSubObjects)
                        {
                            _subObjectSelectionBefore.Add(new SubObjectSelection
                            {
                                ObjectId = obj.Id.ToString(),
                                ComponentType = ci.ComponentIndexType.ToString(),
                                ComponentIndex = ci.Index
                            });

                            // Capture reference plane for before/after transform computation
                            if (brep != null)
                            {
                                string key = $"{obj.Id}:{ci.ComponentIndexType}:{ci.Index}";
                                Plane plane = GetSubObjectPlane(brep, ci);
                                if (plane.IsValid)
                                {
                                    _subObjectPlanesBefore[key] = plane;
                                }
                            }
                        }
                    }
                }

                // Capture initial prompt and enable command window capture
                _initialPrompt = RhinoApp.CommandPrompt;
                _wasCapturingBefore = RhinoApp.CommandWindowCaptureEnabled;
                RhinoApp.CommandWindowCaptureEnabled = true;

                _pendingUserCommand = new CommandRecord
                {
                    Source = CommandSource.User,
                    CommandName = e.CommandEnglishName,
                    RawInput = e.CommandEnglishName,
                    Dialogue = new List<DialogueStep>()
                };

                // Add initial prompt as first dialogue step
                if (!string.IsNullOrEmpty(_initialPrompt) && _initialPrompt != "Command")
                {
                    _pendingUserCommand.Dialogue.Add(new DialogueStep
                    {
                        Prompt = _initialPrompt,
                        Options = ParseOptionsFromPrompt(_initialPrompt),
                        DefaultValue = ParseDefaultFromPrompt(_initialPrompt),
                        Timestamp = DateTime.UtcNow
                    });
                }

                _commandStopwatch = Stopwatch.StartNew();
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"SessionRecorder: Error in OnCommandBegin - {ex.Message}");
            }
        }

        private void OnCommandEnd(object sender, CommandEventArgs e)
        {
            if (_currentSession == null || _pendingUserCommand == null) return;

            // Skip if this is triggered by an MCP request
            if (_isMcpRequest) return;

            // Skip save commands — must not touch doc.Objects during save serialization
            var cmdName = e.CommandEnglishName?.ToLower() ?? "";
            if (cmdName == "save" || cmdName == "savesmall" ||
                cmdName == "saveas" || cmdName == "savesmallas" ||
                cmdName == "incrementalsave") return;

            // Skip expensive processing for block-related commands (they fire many rapid sub-commands)
            // Also skip AIGumball/AIGumballDrag — they record via RecordAIGumballCommand()
            if (cmdName == "aigumball" || cmdName == "aigumballdrag" ||
                cmdName.Contains("block") || cmdName.Contains("instance") ||
                cmdName == "editblockdefinition" || cmdName == "blockedit")
            {
                _pendingUserCommand = null;
                _commandStopwatch = null;
                _objectsBefore.Clear();
                _selectionBefore.Clear();
                _subObjectSelectionBefore.Clear();
                _subObjectPlanesBefore.Clear();
                _transformingSubObjects.Clear();
                try { RhinoApp.CommandWindowCaptureEnabled = _wasCapturingBefore; } catch { }
                return;
            }

            lock (_lock)
            {
                try
                {
                    _commandStopwatch?.Stop();

                    // Capture command window strings before restoring state
                    string[]? capturedStrings = null;
                    try
                    {
                        capturedStrings = RhinoApp.CapturedCommandWindowStrings(true); // true = clear after getting
                    }
                    catch { /* Ignore errors getting captured strings */ }

                    // Restore command window capture state
                    RhinoApp.CommandWindowCaptureEnabled = _wasCapturingBefore;

                    // Parse captured strings into dialogue steps
                    if (capturedStrings != null && capturedStrings.Length > 0 && _pendingUserCommand.Dialogue != null)
                    {
                        ParseCapturedStringsIntoDialogue(capturedStrings, _pendingUserCommand.Dialogue);
                    }

                    // Remove empty dialogue list
                    if (_pendingUserCommand.Dialogue?.Count == 0)
                    {
                        _pendingUserCommand.Dialogue = null;
                    }

                    var doc = RhinoDoc.ActiveDoc;
                    if (doc == null) return;

                    _sequenceNumber++;
                    _pendingUserCommand.Id = $"cmd_{_sequenceNumber:D4}";
                    _pendingUserCommand.SequenceNumber = _sequenceNumber;
                    _pendingUserCommand.Timestamp = DateTime.UtcNow;
                    _pendingUserCommand.Success = (e.CommandResult == Result.Success);
                    _pendingUserCommand.DurationMs = _commandStopwatch?.Elapsed.TotalMilliseconds ?? 0;

                    // Track object changes
                    var objectsAfter = new HashSet<Guid>(doc.Objects.Select(o => o.Id));

                    // Objects created = in after but not in before
                    var created = objectsAfter.Except(_objectsBefore).ToList();
                    if (created.Any())
                    {
                        _pendingUserCommand.ObjectIdsCreated = created.Select(g => g.ToString()).ToList();

                        // Extract geometry parameters synchronously on the main thread.
                        // Must NOT use Task.Run here — accessing RhinoDoc.ActiveDoc,
                        // doc.Objects, .Geometry, .GetBoundingBox from a background thread
                        // races with Rhino's file-save serialization and causes
                        // "_SaveSmall: temporary file could not be renamed" failures.
                        try
                        {
                            var extracted = ExtractGeometryParameters(
                                _pendingUserCommand.ObjectIdsCreated.ToList());
                            if (extracted != null)
                                _pendingUserCommand.ActualParameters = extracted;
                        }
                        catch (Exception ex)
                        {
                            System.Diagnostics.Debug.WriteLine(
                                $"SessionRecorder: Geometry extraction failed - {ex.Message}");
                        }
                    }

                    // Objects deleted = in before but not in after
                    var deleted = _objectsBefore.Except(objectsAfter).ToList();
                    if (deleted.Any())
                    {
                        _pendingUserCommand.ObjectIdsDeleted = deleted.Select(g => g.ToString()).ToList();
                    }

                    // Input objects = what was selected when command started
                    // This enables building object genealogy graphs (inputs → command → outputs)
                    if (_selectionBefore.Any())
                    {
                        _pendingUserCommand.InputObjectIds = _selectionBefore.Select(g => g.ToString()).ToList();
                    }

                    // Sub-object selections (edges, faces, vertices)
                    // This enables tracking which specific sub-components were selected for commands like FilletEdge
                    if (_subObjectSelectionBefore.Any())
                    {
                        _pendingUserCommand.InputSubObjects = new List<SubObjectSelection>(_subObjectSelectionBefore);
                    }

                    // Transformed sub-objects = what was being transformed (from BeforeTransformObjects event)
                    // This is more accurate than InputSubObjects for Gumball operations
                    if (_transformingSubObjects.Any())
                    {
                        _pendingUserCommand.TransformedSubObjects = new List<SubObjectSelection>(_transformingSubObjects);
                    }

                    // Store the transform matrix
                    // Priority 1: Use transform from BeforeTransformObjects event (if it fired)
                    // Priority 2: Compute transform by comparing sub-object planes before/after
                    if (_capturedTransform.HasValue && _capturedTransform.Value.IsValid)
                    {
                        var xform = _capturedTransform.Value;
                        _pendingUserCommand.TransformMatrix = new double[]
                        {
                            xform.M00, xform.M01, xform.M02, xform.M03,
                            xform.M10, xform.M11, xform.M12, xform.M13,
                            xform.M20, xform.M21, xform.M22, xform.M23,
                            xform.M30, xform.M31, xform.M32, xform.M33
                        };
                    }
                    else if (_subObjectPlanesBefore.Count > 0)
                    {
                        // Compute transform by comparing sub-object geometry before/after
                        foreach (var kvp in _subObjectPlanesBefore)
                        {
                            string key = kvp.Key;
                            Plane planeBefore = kvp.Value;

                            // Parse key to get object and component
                            var parts = key.Split(':');
                            if (parts.Length != 3) continue;

                            if (!Guid.TryParse(parts[0], out Guid objId)) continue;
                            if (!Enum.TryParse<ComponentIndexType>(parts[1], out var ciType)) continue;
                            if (!int.TryParse(parts[2], out int index)) continue;

                            var rhinoObj = doc.Objects.FindId(objId);
                            if (rhinoObj == null) continue;

                            var brep = rhinoObj.Geometry as Brep;
                            if (brep == null) continue;

                            ComponentIndex ci = new ComponentIndex(ciType, index);
                            Plane planeAfter = GetSubObjectPlane(brep, ci);

                            if (planeAfter.IsValid && planeBefore.IsValid)
                            {
                                // Compute the transform that maps planeBefore to planeAfter
                                Transform xform = Transform.PlaneToPlane(planeBefore, planeAfter);

                                if (xform.IsValid && !xform.IsIdentity)
                                {
                                    _pendingUserCommand.TransformMatrix = new double[]
                                    {
                                        xform.M00, xform.M01, xform.M02, xform.M03,
                                        xform.M10, xform.M11, xform.M12, xform.M13,
                                        xform.M20, xform.M21, xform.M22, xform.M23,
                                        xform.M30, xform.M31, xform.M32, xform.M33
                                    };
                                    break; // Use first valid transform
                                }
                            }
                        }
                    }

                    _pendingUserCommand.ObjectCountBefore = _objectsBefore.Count;
                    _pendingUserCommand.ObjectCountAfter = objectsAfter.Count;

                    // Add to session
                    _currentSession.Commands.Add(_pendingUserCommand);

                    // Auto-save periodically
                    if (_currentSession.Commands.Count % 10 == 0)
                    {
                        SaveSession();
                    }

                    CommandRecorded?.Invoke(this, new CommandRecordedEventArgs { Record = _pendingUserCommand });
                }
                catch (Exception ex)
                {
                    RhinoApp.WriteLine($"SessionRecorder: Error in OnCommandEnd - {ex.Message}");
                }
                finally
                {
                    _pendingUserCommand = null;
                    _commandStopwatch = null;
                    _objectsBefore.Clear();
                    _selectionBefore.Clear();
                    _subObjectSelectionBefore.Clear();
                    _transformingSubObjects.Clear();
                    _capturedTransform = null;
                    _subObjectPlanesBefore.Clear();
                }
            }
        }

        /// <summary>
        /// Captures sub-object selections just before a transform operation.
        /// This fires for Gumball drags and transform commands on sub-objects.
        /// NOTE: This may fire BEFORE OnCommandBegin for Gumball operations,
        /// so we capture data regardless of _pendingUserCommand state.
        /// </summary>
        private void OnBeforeTransformObjects(object sender, RhinoTransformObjectsEventArgs e)
        {
            // Skip if not recording or MCP request
            if (_currentSession == null || _isMcpRequest) return;

            try
            {
                // Capture the transform matrix
                _capturedTransform = e.Transform;
                RhinoApp.WriteLine($"SessionRecorder: BeforeTransformObjects fired! Transform captured. Objects: {e.ObjectCount}");

                // Don't clear sub-objects - accumulate in case multiple transforms happen during one command
                // Will be cleared in OnCommandEnd's finally block

                foreach (var rhinoObj in e.Objects)
                {
                    if (rhinoObj == null) continue;

                    var selectedSubObjects = rhinoObj.GetSelectedSubObjects();
                    if (selectedSubObjects != null && selectedSubObjects.Length > 0)
                    {
                        foreach (var ci in selectedSubObjects)
                        {
                            _transformingSubObjects.Add(new SubObjectSelection
                            {
                                ObjectId = rhinoObj.Id.ToString(),
                                ComponentType = ci.ComponentIndexType.ToString(),
                                ComponentIndex = ci.Index
                            });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"SessionRecorder: Error in OnBeforeTransformObjects - {ex.Message}");
            }
        }

        private void OnDocumentOpened(object sender, DocumentOpenEventArgs e)
        {
            // Start a new session for the opened document
            if (e.Document != null)
            {
                StartSession(e.Document);
            }
        }

        private void OnDocumentClosing(object sender, DocumentEventArgs e)
        {
            // End session when document closes
            if (_currentSession != null && e.Document != null)
            {
                // Check if it's the same document
                var currentDocPath = _currentSession.Document.Path;
                var closingDocPath = e.Document.Path ?? "";

                if (string.Equals(currentDocPath, closingDocPath, StringComparison.OrdinalIgnoreCase) ||
                    string.IsNullOrEmpty(currentDocPath))
                {
                    EndSession("document_closed");
                }
            }
        }

        // ==================== Persistence ====================

        private void SaveSession()
        {
            if (_currentSession == null || string.IsNullOrEmpty(_currentSessionFilePath)) return;

            try
            {
                UpdateStats();

                var options = new JsonSerializerOptions
                {
                    WriteIndented = true,
                    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                    Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) }
                };

                var json = JsonSerializer.Serialize(_currentSession, options);
                File.WriteAllText(_currentSessionFilePath, json);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"SessionRecorder: Failed to save session - {ex.Message}");
            }
        }

        private void UpdateStats()
        {
            if (_currentSession == null) return;

            var stats = _currentSession.Stats;
            var commands = _currentSession.Commands;

            stats.TotalCommands = commands.Count;
            stats.McpCommands = commands.Count(c => c.Source == CommandSource.Mcp);
            stats.UserCommands = commands.Count(c => c.Source == CommandSource.User);
            stats.ScriptCommands = commands.Count(c => c.Source == CommandSource.Script);
            stats.SuccessfulCommands = commands.Count(c => c.Success);
            stats.FailedCommands = commands.Count(c => !c.Success);
            stats.ObjectsCreated = commands.Sum(c => c.ObjectIdsCreated?.Count ?? 0);
            stats.ObjectsDeleted = commands.Sum(c => c.ObjectIdsDeleted?.Count ?? 0);
            stats.GumballCommands = commands.Count(c => c.CommandName == "AIGumball");
            stats.TotalGumballDrags = commands.Where(c => c.CommandName == "AIGumball").Sum(c => c.GumballDragCount);
        }

        // ==================== Helpers ====================

        private void CaptureGitInfo(SessionData session, string? documentPath)
        {
            if (string.IsNullOrEmpty(documentPath)) return;

            var directory = Path.GetDirectoryName(documentPath);
            if (string.IsNullOrEmpty(directory)) return;

            try
            {
                var gitDir = SessionPaths.FindGitRoot(directory);
                if (gitDir == null) return;

                // Get current branch
                var headPath = Path.Combine(gitDir, "HEAD");
                if (File.Exists(headPath))
                {
                    var headContent = File.ReadAllText(headPath).Trim();
                    if (headContent.StartsWith("ref: refs/heads/"))
                    {
                        session.GitBranch = headContent.Substring("ref: refs/heads/".Length);

                        // Get commit from branch ref
                        var branchPath = Path.Combine(gitDir, "refs", "heads", session.GitBranch);
                        if (File.Exists(branchPath))
                        {
                            var commit = File.ReadAllText(branchPath).Trim();
                            session.GitCommit = commit.Length >= 7 ? commit.Substring(0, 7) : commit;
                        }
                    }
                    else if (headContent.Length >= 7)
                    {
                        // Detached HEAD state
                        session.GitCommit = headContent.Substring(0, 7);
                    }
                }
            }
            catch
            {
                // Ignore git errors
            }
        }

        /// <summary>
        /// Try to extract object IDs from response data.
        /// Handles various response formats from different endpoints.
        /// </summary>
        private static void ExtractCreatedObjectIds(CommandRecord record, object responseData)
        {
            try
            {
                // Serialize and re-parse as JsonElement for consistent access
                var json = JsonSerializer.Serialize(responseData);
                using var doc = JsonDocument.Parse(json);
                var root = doc.RootElement;

                var ids = new List<string>();

                // Object with "objectIds" array (e.g., /command response)
                if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("objectIds", out var objectIdsProp) && objectIdsProp.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in objectIdsProp.EnumerateArray())
                    {
                        var id = item.GetString();
                        if (!string.IsNullOrEmpty(id))
                        {
                            ids.Add(id);
                        }
                    }
                }
                // Single object with "id" property (e.g., /create response)
                else if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("id", out var idProp))
                {
                    var id = idProp.GetString();
                    if (!string.IsNullOrEmpty(id))
                    {
                        ids.Add(id);
                    }
                }
                // Array of objects with "id" property
                else if (root.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in root.EnumerateArray())
                    {
                        if (item.ValueKind == JsonValueKind.Object && item.TryGetProperty("id", out var itemId))
                        {
                            var id = itemId.GetString();
                            if (!string.IsNullOrEmpty(id))
                            {
                                ids.Add(id);
                            }
                        }
                    }
                }
                // Object with "ids" array property (e.g., boolean operations)
                else if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("ids", out var idsProp) && idsProp.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in idsProp.EnumerateArray())
                    {
                        var id = item.GetString();
                        if (!string.IsNullOrEmpty(id))
                        {
                            ids.Add(id);
                        }
                    }
                }
                // Object with "objects" array
                else if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("objects", out var objectsProp) && objectsProp.ValueKind == JsonValueKind.Array)
                {
                    foreach (var item in objectsProp.EnumerateArray())
                    {
                        if (item.ValueKind == JsonValueKind.Object && item.TryGetProperty("id", out var objId))
                        {
                            var id = objId.GetString();
                            if (!string.IsNullOrEmpty(id))
                            {
                                ids.Add(id);
                            }
                        }
                    }
                }

                if (ids.Count > 0)
                {
                    record.ObjectIdsCreated = ids;
                }
            }
            catch
            {
                // Ignore parse errors - not all responses contain IDs
            }
        }

        private static string ExtractCommandName(string endpoint)
        {
            // Convert endpoint like "/command" or "/create" to a readable name
            if (string.IsNullOrEmpty(endpoint)) return "unknown";

            var name = endpoint.TrimStart('/').ToLowerInvariant();

            // Map common endpoints to readable names
            return name switch
            {
                "command" => "rhino_command",
                "execute" => "rhino_execute",
                "create" => "rhino_create",
                "delete" => "rhino_delete",
                "select" => "rhino_select",
                "transform" => "rhino_transform",
                "boolean" => "rhino_boolean",
                "layers" => "rhino_layers",
                "viewport" => "rhino_viewport",
                _ => $"rhino_{name}"
            };
        }

        /// <summary>
        /// Parses options from a prompt string.
        /// Options are typically in parentheses: "Center of circle ( Diameter Circumference )"
        /// </summary>
        private static List<string>? ParseOptionsFromPrompt(string? prompt)
        {
            if (string.IsNullOrEmpty(prompt)) return null;

            // Find text in parentheses
            int start = prompt.IndexOf('(');
            int end = prompt.LastIndexOf(')');

            if (start >= 0 && end > start)
            {
                var options = new List<string>();
                var optionsText = prompt.Substring(start + 1, end - start - 1);
                var parts = optionsText.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
                foreach (var part in parts)
                {
                    if (!string.IsNullOrWhiteSpace(part))
                    {
                        options.Add(part.Trim());
                    }
                }
                return options.Count > 0 ? options : null;
            }

            return null;
        }

        /// <summary>
        /// Parses default value from a prompt string.
        /// Default is typically in angle brackets: "Radius <5.00>"
        /// </summary>
        private static string? ParseDefaultFromPrompt(string? prompt)
        {
            if (string.IsNullOrEmpty(prompt)) return null;

            int start = prompt.IndexOf('<');
            int end = prompt.LastIndexOf('>');

            if (start >= 0 && end > start)
            {
                return prompt.Substring(start + 1, end - start - 1);
            }

            return null;
        }

        /// <summary>
        /// Extract actual parameters from created geometry objects.
        /// Queries the geometry by GUID and extracts dimensions, positions, etc.
        /// </summary>
        private static Dictionary<string, object>? ExtractGeometryParameters(List<string> objectIds)
        {
            if (objectIds == null || objectIds.Count == 0) return null;

            var doc = RhinoDoc.ActiveDoc;
            if (doc == null) return null;

            var allParams = new Dictionary<string, object>();
            var objectsData = new List<Dictionary<string, object>>();

            foreach (var idStr in objectIds)
            {
                if (!Guid.TryParse(idStr, out var guid)) continue;

                var rhinoObj = doc.Objects.FindId(guid);
                if (rhinoObj == null) continue;

                var geometry = rhinoObj.Geometry;
                if (geometry == null) continue;

                var objParams = new Dictionary<string, object>
                {
                    ["id"] = idStr,
                    ["type"] = geometry.ObjectType.ToString()
                };

                // Get bounding box for all geometry types
                var bbox = geometry.GetBoundingBox(true);
                if (bbox.IsValid)
                {
                    objParams["boundingBox"] = new
                    {
                        min = new[] { bbox.Min.X, bbox.Min.Y, bbox.Min.Z },
                        max = new[] { bbox.Max.X, bbox.Max.Y, bbox.Max.Z },
                        width = bbox.Max.X - bbox.Min.X,
                        depth = bbox.Max.Y - bbox.Min.Y,
                        height = bbox.Max.Z - bbox.Min.Z
                    };
                }

                // Extract type-specific parameters
                switch (geometry)
                {
                    case Rhino.Geometry.Brep brep:
                        ExtractBrepParameters(brep, objParams);
                        break;

                    case Rhino.Geometry.Extrusion extrusion:
                        ExtractExtrusionParameters(extrusion, objParams);
                        break;

                    case Rhino.Geometry.Curve curve:
                        ExtractCurveParameters(curve, objParams);
                        break;

                    case Rhino.Geometry.Mesh mesh:
                        objParams["vertexCount"] = mesh.Vertices.Count;
                        objParams["faceCount"] = mesh.Faces.Count;
                        break;

                    case Rhino.Geometry.Point point:
                        objParams["location"] = new[] { point.Location.X, point.Location.Y, point.Location.Z };
                        break;
                }

                objectsData.Add(objParams);
            }

            if (objectsData.Count == 0) return null;

            // If single object, flatten the parameters
            if (objectsData.Count == 1)
            {
                return objectsData[0];
            }

            // Multiple objects - return as array
            allParams["objects"] = objectsData;
            allParams["count"] = objectsData.Count;
            return allParams;
        }

        /// <summary>
        /// Extract parameters from a Brep (surface/solid).
        /// Attempts to identify if it's a primitive shape (sphere, box, cylinder, etc.)
        /// </summary>
        private static void ExtractBrepParameters(Rhino.Geometry.Brep brep, Dictionary<string, object> objParams)
        {
            objParams["faceCount"] = brep.Faces.Count;
            objParams["edgeCount"] = brep.Edges.Count;
            objParams["isSolid"] = brep.IsSolid;

            // Try to identify primitive shapes
            if (brep.Faces.Count == 1)
            {
                var face = brep.Faces[0];
                var surface = face.UnderlyingSurface();

                // Check for sphere
                if (surface.TryGetSphere(out var sphere))
                {
                    objParams["primitiveType"] = "Sphere";
                    objParams["center"] = new[] { sphere.Center.X, sphere.Center.Y, sphere.Center.Z };
                    objParams["radius"] = sphere.Radius;
                    return;
                }

                // Check for cylinder
                if (surface.TryGetCylinder(out var cylinder))
                {
                    objParams["primitiveType"] = "Cylinder";
                    objParams["center"] = new[] { cylinder.Center.X, cylinder.Center.Y, cylinder.Center.Z };
                    objParams["radius"] = cylinder.CircleAt(0).Radius;
                    objParams["axis"] = new[] { cylinder.Axis.X, cylinder.Axis.Y, cylinder.Axis.Z };
                    return;
                }

                // Check for cone
                if (surface.TryGetCone(out var cone))
                {
                    objParams["primitiveType"] = "Cone";
                    objParams["apex"] = new[] { cone.ApexPoint.X, cone.ApexPoint.Y, cone.ApexPoint.Z };
                    objParams["baseRadius"] = cone.Radius;
                    objParams["height"] = cone.Height;
                    return;
                }

                // Check for torus
                if (surface.TryGetTorus(out var torus))
                {
                    objParams["primitiveType"] = "Torus";
                    objParams["center"] = new[] { torus.Plane.Origin.X, torus.Plane.Origin.Y, torus.Plane.Origin.Z };
                    objParams["majorRadius"] = torus.MajorRadius;
                    objParams["minorRadius"] = torus.MinorRadius;
                    return;
                }
            }

            // Check if it's a box (6 planar faces)
            if (brep.Faces.Count == 6 && brep.IsSolid)
            {
                bool allPlanar = true;
                foreach (var face in brep.Faces)
                {
                    if (!face.IsPlanar())
                    {
                        allPlanar = false;
                        break;
                    }
                }
                if (allPlanar)
                {
                    objParams["primitiveType"] = "Box";
                    // Dimensions already captured in bounding box
                }
            }

            // NOTE: Volume/Area calculations commented out - they can be very expensive
            // (VolumeMassProperties.Compute tessellates geometry with no timeout, causing UI freezes)
            // Bounding box dimensions provide adequate size information for most use cases.
            // See: docs/bugs/BLOCK_EDIT_FREEZE_BUG.md
            //
            // var mp = Rhino.Geometry.VolumeMassProperties.Compute(brep);
            // if (mp != null)
            // {
            //     if (brep.IsSolid)
            //     {
            //         objParams["volume"] = mp.Volume;
            //     }
            //     objParams["area"] = Rhino.Geometry.AreaMassProperties.Compute(brep)?.Area;
            //     objParams["centroid"] = new[] { mp.Centroid.X, mp.Centroid.Y, mp.Centroid.Z };
            // }
        }

        /// <summary>
        /// Extract parameters from an Extrusion.
        /// </summary>
        private static void ExtractExtrusionParameters(Rhino.Geometry.Extrusion extrusion, Dictionary<string, object> objParams)
        {
            objParams["isSolid"] = extrusion.IsSolid;

            var path = extrusion.PathLineCurve();
            if (path != null)
            {
                objParams["extrusionHeight"] = path.GetLength();
                objParams["pathStart"] = new[] { path.PointAtStart.X, path.PointAtStart.Y, path.PointAtStart.Z };
                objParams["pathEnd"] = new[] { path.PointAtEnd.X, path.PointAtEnd.Y, path.PointAtEnd.Z };
            }

            // Try to get profile
            var profile = extrusion.Profile3d(0, 0);
            if (profile != null)
            {
                objParams["profileLength"] = profile.GetLength();
                objParams["profileIsClosed"] = profile.IsClosed;
            }
        }

        /// <summary>
        /// Extract parameters from a Curve.
        /// </summary>
        private static void ExtractCurveParameters(Rhino.Geometry.Curve curve, Dictionary<string, object> objParams)
        {
            objParams["length"] = curve.GetLength();
            objParams["isClosed"] = curve.IsClosed;
            objParams["isPlanar"] = curve.IsPlanar();
            objParams["degree"] = curve.Degree;
            objParams["startPoint"] = new[] { curve.PointAtStart.X, curve.PointAtStart.Y, curve.PointAtStart.Z };
            objParams["endPoint"] = new[] { curve.PointAtEnd.X, curve.PointAtEnd.Y, curve.PointAtEnd.Z };

            // Check for circle/arc
            if (curve.TryGetCircle(out var circle))
            {
                objParams["curveType"] = "Circle";
                objParams["center"] = new[] { circle.Center.X, circle.Center.Y, circle.Center.Z };
                objParams["radius"] = circle.Radius;
            }
            else if (curve.TryGetArc(out var arc))
            {
                objParams["curveType"] = "Arc";
                objParams["center"] = new[] { arc.Center.X, arc.Center.Y, arc.Center.Z };
                objParams["radius"] = arc.Radius;
                objParams["angleDegrees"] = arc.AngleDegrees;
            }
            else if (curve.TryGetEllipse(out var ellipse))
            {
                objParams["curveType"] = "Ellipse";
                objParams["center"] = new[] { ellipse.Center.X, ellipse.Center.Y, ellipse.Center.Z };
                objParams["radius1"] = ellipse.Radius1;
                objParams["radius2"] = ellipse.Radius2;
            }
            else if (curve.IsLinear())
            {
                objParams["curveType"] = "Line";
            }
            else if (curve.IsPolyline())
            {
                objParams["curveType"] = "Polyline";
                if (curve.TryGetPolyline(out var polyline))
                {
                    objParams["pointCount"] = polyline.Count;
                }
            }
        }

        /// <summary>
        /// Parse captured command window strings into dialogue steps.
        /// Identifies prompts, user inputs, and command feedback.
        /// </summary>
        private static void ParseCapturedStringsIntoDialogue(string[] capturedStrings, List<DialogueStep> dialogue)
        {
            foreach (var line in capturedStrings)
            {
                if (string.IsNullOrWhiteSpace(line)) continue;

                var trimmed = line.Trim();

                // Skip common noise
                if (trimmed.StartsWith("Command:") ||
                    trimmed == "Command" ||
                    trimmed.Length < 2)
                {
                    continue;
                }

                // Check if this looks like a prompt (contains options in parentheses or default in angle brackets)
                bool hasOptions = trimmed.Contains("(") && trimmed.Contains(")");
                bool hasDefault = trimmed.Contains("<") && trimmed.Contains(">");
                bool looksLikePrompt = hasOptions || hasDefault ||
                                       trimmed.EndsWith(":") ||
                                       trimmed.StartsWith("Select") ||
                                       trimmed.StartsWith("Pick") ||
                                       trimmed.StartsWith("Enter") ||
                                       trimmed.StartsWith("Specify");

                if (looksLikePrompt)
                {
                    // This is a prompt - add as dialogue step
                    dialogue.Add(new DialogueStep
                    {
                        Prompt = trimmed,
                        Options = ParseOptionsFromPrompt(trimmed),
                        DefaultValue = ParseDefaultFromPrompt(trimmed),
                        Timestamp = DateTime.UtcNow
                    });
                }
                else if (dialogue.Count > 0)
                {
                    // This might be user input for the previous prompt
                    var lastStep = dialogue[dialogue.Count - 1];
                    if (string.IsNullOrEmpty(lastStep.Input))
                    {
                        lastStep.Input = trimmed;
                    }
                }
            }
        }

        // ==================== Sub-Object Plane Helpers ====================

        /// <summary>
        /// Get a reference plane from a sub-object for before/after comparison.
        /// </summary>
        private static Plane GetSubObjectPlane(Brep brep, ComponentIndex ci)
        {
            try
            {
                switch (ci.ComponentIndexType)
                {
                    case ComponentIndexType.BrepEdge:
                        if (ci.Index >= 0 && ci.Index < brep.Edges.Count)
                        {
                            var edge = brep.Edges[ci.Index];
                            return CreatePlaneFromEdge(edge);
                        }
                        break;

                    case ComponentIndexType.BrepFace:
                        if (ci.Index >= 0 && ci.Index < brep.Faces.Count)
                        {
                            var face = brep.Faces[ci.Index];
                            double u = face.Domain(0).Mid;
                            double v = face.Domain(1).Mid;
                            if (face.FrameAt(u, v, out Plane facePlane))
                            {
                                return facePlane;
                            }
                        }
                        break;

                    case ComponentIndexType.BrepVertex:
                        if (ci.Index >= 0 && ci.Index < brep.Vertices.Count)
                        {
                            var vertex = brep.Vertices[ci.Index];
                            // Return plane at vertex with world orientation
                            return new Plane(vertex.Location, Vector3d.XAxis, Vector3d.YAxis);
                        }
                        break;
                }
            }
            catch
            {
                // Ignore errors - return invalid plane
            }

            return Plane.Unset;
        }

        /// <summary>
        /// Create a reference plane from an edge.
        /// Origin at midpoint, X along tangent, Y perpendicular.
        /// </summary>
        private static Plane CreatePlaneFromEdge(BrepEdge edge)
        {
            try
            {
                Point3d origin = edge.PointAtNormalizedLength(0.5); // midpoint
                Vector3d tangent = edge.TangentAt(edge.Domain.Mid);
                tangent.Unitize();

                // Create perpendicular vector
                Vector3d perp = Vector3d.CrossProduct(tangent, Vector3d.ZAxis);
                if (perp.IsZero || perp.Length < 0.001)
                {
                    perp = Vector3d.CrossProduct(tangent, Vector3d.XAxis);
                }
                perp.Unitize();

                return new Plane(origin, tangent, perp);
            }
            catch
            {
                return Plane.Unset;
            }
        }

        // ==================== Query Methods ====================

        /// <summary>
        /// Get the current session data.
        /// </summary>
        public SessionData? GetCurrentSession()
        {
            lock (_lock)
            {
                return _currentSession;
            }
        }

        /// <summary>
        /// Get command history from the current session.
        /// </summary>
        public List<CommandRecord> GetHistory(int limit = 100, int offset = 0, CommandSource? sourceFilter = null)
        {
            lock (_lock)
            {
                if (_currentSession == null) return new List<CommandRecord>();

                var query = _currentSession.Commands.AsEnumerable();

                if (sourceFilter.HasValue)
                {
                    query = query.Where(c => c.Source == sourceFilter.Value);
                }

                return query.Skip(offset).Take(limit).ToList();
            }
        }

        /// <summary>
        /// List available sessions from disk.
        /// </summary>
        public List<SessionSummary> ListSessions(string? projectFilter = null, int limit = 50)
        {
            var summaries = new List<SessionSummary>();

            try
            {
                if (!Directory.Exists(SessionPaths.BaseFolder))
                    return summaries;

                var sessionFiles = Directory.GetFiles(SessionPaths.BaseFolder, "session_*.json", SearchOption.AllDirectories)
                    .OrderByDescending(f => File.GetLastWriteTimeUtc(f))
                    .Take(limit * 2); // Get more than needed to account for filtering

                foreach (var file in sessionFiles)
                {
                    try
                    {
                        var json = File.ReadAllText(file);
                        var session = JsonSerializer.Deserialize<SessionData>(json, new JsonSerializerOptions
                        {
                            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
                        });

                        if (session == null) continue;

                        // Apply project filter
                        if (!string.IsNullOrEmpty(projectFilter) &&
                            session.Document.ProjectFolder.IndexOf(projectFilter, StringComparison.OrdinalIgnoreCase) < 0)
                        {
                            continue;
                        }

                        summaries.Add(new SessionSummary
                        {
                            Id = session.Id,
                            DocumentName = session.Document.Name,
                            ProjectFolder = session.Document.ProjectFolder,
                            StartedAt = session.StartedAt,
                            EndedAt = session.EndedAt,
                            CommandCount = session.Commands.Count,
                            FilePath = file
                        });

                        if (summaries.Count >= limit) break;
                    }
                    catch
                    {
                        // Skip files that can't be read
                    }
                }
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine($"SessionRecorder: Error listing sessions - {ex.Message}");
            }

            return summaries;
        }
    }
}
