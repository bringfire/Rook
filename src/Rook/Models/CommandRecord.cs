using System;
using System.Collections.Generic;

namespace Rook.Models
{
    /// <summary>
    /// A sub-object selection (edge, face, vertex) within a parent object.
    /// </summary>
    public class SubObjectSelection
    {
        /// <summary>
        /// GUID of the parent object containing the sub-object.
        /// </summary>
        public string ObjectId { get; set; } = "";

        /// <summary>
        /// Type of sub-object: BrepEdge, BrepFace, BrepVertex, MeshFace, MeshVertex, etc.
        /// </summary>
        public string ComponentType { get; set; } = "";

        /// <summary>
        /// Index of the sub-object within the parent (e.g., edge index in Brep.Edges).
        /// </summary>
        public int ComponentIndex { get; set; }
    }

    /// <summary>
    /// A single step in a command dialogue (prompt and response).
    /// </summary>
    public class DialogueStep
    {
        /// <summary>
        /// The prompt text shown by Rhino.
        /// </summary>
        public string Prompt { get; set; } = "";

        /// <summary>
        /// Available options parsed from prompt (text in parentheses).
        /// </summary>
        public List<string>? Options { get; set; }

        /// <summary>
        /// Default value parsed from prompt (text in angle brackets).
        /// </summary>
        public string? DefaultValue { get; set; }

        /// <summary>
        /// The input provided (user typed or selected).
        /// </summary>
        public string? Input { get; set; }

        /// <summary>
        /// Timestamp when this prompt appeared.
        /// </summary>
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    }

    /// <summary>
    /// Source of a command - where it originated from.
    /// </summary>
    public enum CommandSource
    {
        /// <summary>
        /// Command came from AI via MCP tool call.
        /// </summary>
        Mcp,

        /// <summary>
        /// User typed command directly in Rhino.
        /// </summary>
        User,

        /// <summary>
        /// Command executed via Python script.
        /// </summary>
        Script,

        /// <summary>
        /// Unknown or system command.
        /// </summary>
        Unknown
    }

    /// <summary>
    /// A single command execution record.
    /// Captures both MCP tool calls and user-initiated Rhino commands.
    /// </summary>
    public class CommandRecord
    {
        /// <summary>
        /// Unique ID within the session (e.g., "cmd_001").
        /// </summary>
        public string Id { get; set; } = "";

        /// <summary>
        /// Sequential order in the session (1-based).
        /// </summary>
        public int SequenceNumber { get; set; }

        /// <summary>
        /// When the command was executed.
        /// </summary>
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;

        /// <summary>
        /// Where the command originated from.
        /// </summary>
        public CommandSource Source { get; set; } = CommandSource.Unknown;

        /// <summary>
        /// Command name (e.g., "rhino_command", "Box", "_Line").
        /// For MCP: the tool name or endpoint.
        /// For User: the Rhino command name.
        /// </summary>
        public string CommandName { get; set; } = "";

        /// <summary>
        /// Raw input string (full command or MCP request body).
        /// </summary>
        public string? RawInput { get; set; }

        /// <summary>
        /// Parsed parameters (for structured access).
        /// </summary>
        public Dictionary<string, object>? Parameters { get; set; }

        /// <summary>
        /// HTTP endpoint called (for MCP commands).
        /// </summary>
        public string? Endpoint { get; set; }

        /// <summary>
        /// Object count before command execution.
        /// </summary>
        public int ObjectCountBefore { get; set; }

        /// <summary>
        /// Object count after command execution.
        /// </summary>
        public int ObjectCountAfter { get; set; }

        /// <summary>
        /// Whether the command succeeded.
        /// </summary>
        public bool Success { get; set; }

        /// <summary>
        /// Response data (API response or command result).
        /// </summary>
        public object? Response { get; set; }

        /// <summary>
        /// GUIDs of objects created by this command.
        /// </summary>
        public List<string>? ObjectIdsCreated { get; set; }

        /// <summary>
        /// GUIDs of objects modified by this command.
        /// </summary>
        public List<string>? ObjectIdsModified { get; set; }

        /// <summary>
        /// GUIDs of objects deleted by this command.
        /// </summary>
        public List<string>? ObjectIdsDeleted { get; set; }

        /// <summary>
        /// GUIDs of objects that were selected when the command started.
        /// These are the input objects that the command operated on.
        /// Enables building object genealogy graphs (inputs → command → outputs).
        /// </summary>
        public List<string>? InputObjectIds { get; set; }

        /// <summary>
        /// Sub-object selections (edges, faces, vertices) when the command started.
        /// Captures which specific sub-components were selected for commands like FilletEdge.
        /// </summary>
        public List<SubObjectSelection>? InputSubObjects { get; set; }

        /// <summary>
        /// Sub-objects that were being transformed when BeforeTransformObjects fired.
        /// Captures which edges/faces/vertices were selected during Gumball operations.
        /// Different from InputSubObjects which captures selection at command start.
        /// </summary>
        public List<SubObjectSelection>? TransformedSubObjects { get; set; }

        /// <summary>
        /// The transformation matrix applied during this command.
        /// Captured from BeforeTransformObjects event.
        /// Stored as a 4x4 matrix (16 doubles) in row-major order.
        /// </summary>
        public double[]? TransformMatrix { get; set; }

        /// <summary>
        /// Error message if command failed.
        /// </summary>
        public string? ErrorMessage { get; set; }

        /// <summary>
        /// Command line dialogue captured during execution.
        /// Contains prompts, options, defaults, and user inputs.
        /// </summary>
        public List<DialogueStep>? Dialogue { get; set; }

        /// <summary>
        /// Actual parameters extracted from created geometry.
        /// Contains dimensions, positions, and other measurable values.
        /// </summary>
        public Dictionary<string, object>? ActualParameters { get; set; }

        /// <summary>
        /// Detailed gumball drag history (only populated for AIGumball commands).
        /// Each entry represents one completed drag operation with handle mode,
        /// delta transform, and cumulative transform.
        /// </summary>
        public List<GumballDragRecord>? GumballDrags { get; set; }

        /// <summary>
        /// The gumball handle mode for the overall command (first drag's mode, for quick filtering).
        /// Only set for AIGumball commands.
        /// </summary>
        public string? GumballMode { get; set; }

        /// <summary>
        /// Total number of gumball drags in this command.
        /// Only set for AIGumball commands.
        /// </summary>
        public int GumballDragCount { get; set; }

        /// <summary>
        /// Execution duration in milliseconds.
        /// </summary>
        public double DurationMs { get; set; }

        /// <summary>
        /// Whether this command can be replayed.
        /// Some commands (like interactive picking) cannot be replayed.
        /// </summary>
        public bool CanReplay { get; set; } = true;

        /// <summary>
        /// Helper to compute objects created count.
        /// Uses ObjectIdsCreated list if available, otherwise computes from before/after counts.
        /// </summary>
        public int ObjectsCreatedCount => ObjectIdsCreated?.Count ?? Math.Max(0, ObjectCountAfter - ObjectCountBefore);
    }
}
