using System;
using System.Collections.Generic;

namespace Rook.Models
{
    /// <summary>
    /// Represents a complete recording session tied to a Rhino document.
    /// Contains all commands (MCP + user) executed during the session.
    /// </summary>
    public class SessionData
    {
        public string Id { get; set; } = Guid.NewGuid().ToString("N").Substring(0, 12);
        public DateTime StartedAt { get; set; } = DateTime.UtcNow;
        public DateTime? EndedAt { get; set; }
        public string EndReason { get; set; } = "";

        /// <summary>
        /// Document this session is bound to.
        /// </summary>
        public DocumentInfo Document { get; set; } = new();

        /// <summary>
        /// All commands recorded in this session, in order.
        /// </summary>
        public List<CommandRecord> Commands { get; set; } = new();

        /// <summary>
        /// Aggregate statistics for the session.
        /// </summary>
        public SessionStats Stats { get; set; } = new();

        /// <summary>
        /// Git branch at session start (if in a git repo).
        /// </summary>
        public string? GitBranch { get; set; }

        /// <summary>
        /// Git commit hash at session start (short form).
        /// </summary>
        public string? GitCommit { get; set; }

        /// <summary>
        /// Schema version for forward compatibility.
        /// </summary>
        public string Version { get; set; } = "1.1";
    }

    /// <summary>
    /// Information about the Rhino document associated with a session.
    /// </summary>
    public class DocumentInfo
    {
        /// <summary>
        /// Document filename (e.g., "ChairDesign.3dm").
        /// </summary>
        public string Name { get; set; } = "";

        /// <summary>
        /// Full path to the document (empty if unsaved).
        /// </summary>
        public string Path { get; set; } = "";

        /// <summary>
        /// Document units (e.g., "Millimeters", "Meters").
        /// </summary>
        public string Units { get; set; } = "";

        /// <summary>
        /// Project folder name (parent directory), used for organizing sessions.
        /// </summary>
        public string ProjectFolder { get; set; } = "";
    }

    /// <summary>
    /// Aggregate statistics for a session.
    /// </summary>
    public class SessionStats
    {
        public int TotalCommands { get; set; }
        public int McpCommands { get; set; }
        public int UserCommands { get; set; }
        public int ScriptCommands { get; set; }
        public int SuccessfulCommands { get; set; }
        public int FailedCommands { get; set; }
        public int ObjectsCreated { get; set; }
        public int ObjectsDeleted { get; set; }
        public int GumballCommands { get; set; }
        public int TotalGumballDrags { get; set; }
    }

    /// <summary>
    /// Summary info for listing sessions without loading full data.
    /// </summary>
    public class SessionSummary
    {
        public string Id { get; set; } = "";
        public string DocumentName { get; set; } = "";
        public string ProjectFolder { get; set; } = "";
        public DateTime StartedAt { get; set; }
        public DateTime? EndedAt { get; set; }
        public int CommandCount { get; set; }
        public string FilePath { get; set; } = "";
    }
}
