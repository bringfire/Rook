using System;
using System.IO;
using System.Text.RegularExpressions;
using Rook.Models;

namespace Rook
{
    /// <summary>
    /// Utility class for session file path management.
    /// Sessions are stored in %APPDATA%/Rook/sessions/ organized by project and document.
    /// </summary>
    public static class SessionPaths
    {
        /// <summary>
        /// Base folder for all session data.
        /// </summary>
        public static string BaseFolder => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "Rook",
            "sessions"
        );

        /// <summary>
        /// Path to the sessions index file.
        /// </summary>
        public static string IndexFilePath => Path.Combine(BaseFolder, "sessions_index.json");

        /// <summary>
        /// Gets the folder for a specific document's sessions.
        /// Structure: BaseFolder/ProjectName/DocumentName/
        /// </summary>
        public static string GetSessionFolder(DocumentInfo doc)
        {
            var projectName = string.IsNullOrWhiteSpace(doc.ProjectFolder)
                ? "Unsaved"
                : SanitizeFileName(doc.ProjectFolder);

            var docName = string.IsNullOrWhiteSpace(doc.Name)
                ? "Untitled"
                : SanitizeFileName(Path.GetFileNameWithoutExtension(doc.Name));

            return Path.Combine(BaseFolder, projectName, docName);
        }

        /// <summary>
        /// Gets the full path for a session file.
        /// </summary>
        public static string GetSessionFilePath(DocumentInfo doc, DateTime sessionStart)
        {
            var folder = GetSessionFolder(doc);
            var timestamp = sessionStart.ToString("yyyy-MM-dd_HH-mm-ss");
            return Path.Combine(folder, $"session_{timestamp}.json");
        }

        /// <summary>
        /// Gets the full path for a session file by ID.
        /// </summary>
        public static string GetSessionFilePath(DocumentInfo doc, string sessionId)
        {
            var folder = GetSessionFolder(doc);
            return Path.Combine(folder, $"session_{sessionId}.json");
        }

        /// <summary>
        /// Ensures the session folder exists for a document.
        /// </summary>
        public static void EnsureSessionFolder(DocumentInfo doc)
        {
            var folder = GetSessionFolder(doc);
            if (!Directory.Exists(folder))
            {
                Directory.CreateDirectory(folder);
            }
        }

        /// <summary>
        /// Ensures the base sessions folder exists.
        /// </summary>
        public static void EnsureBaseFolder()
        {
            if (!Directory.Exists(BaseFolder))
            {
                Directory.CreateDirectory(BaseFolder);
            }
        }

        /// <summary>
        /// Extracts the project folder name from a document path.
        /// Returns the parent directory name, or empty string if unavailable.
        /// </summary>
        public static string ExtractProjectFolder(string documentPath)
        {
            if (string.IsNullOrWhiteSpace(documentPath))
                return "";

            try
            {
                var directory = Path.GetDirectoryName(documentPath);
                if (!string.IsNullOrEmpty(directory))
                {
                    return new DirectoryInfo(directory).Name;
                }
            }
            catch
            {
                // Ignore path parsing errors
            }

            return "";
        }

        /// <summary>
        /// Sanitizes a string for use as a filename.
        /// Removes or replaces invalid characters.
        /// </summary>
        public static string SanitizeFileName(string name)
        {
            if (string.IsNullOrWhiteSpace(name))
                return "Unknown";

            // Remove invalid filename characters
            var invalid = new string(Path.GetInvalidFileNameChars());
            var regex = new Regex($"[{Regex.Escape(invalid)}]");
            var sanitized = regex.Replace(name, "_");

            // Trim and limit length
            sanitized = sanitized.Trim().TrimEnd('.');
            if (sanitized.Length > 50)
            {
                sanitized = sanitized.Substring(0, 50);
            }

            return string.IsNullOrWhiteSpace(sanitized) ? "Unknown" : sanitized;
        }

        /// <summary>
        /// Finds the git root directory starting from a given path.
        /// Returns null if not in a git repository.
        /// </summary>
        public static string? FindGitRoot(string startPath)
        {
            try
            {
                var current = startPath;
                while (!string.IsNullOrEmpty(current))
                {
                    var gitDir = Path.Combine(current, ".git");
                    if (Directory.Exists(gitDir))
                    {
                        return gitDir;
                    }
                    var parent = Directory.GetParent(current);
                    current = parent?.FullName;
                }
            }
            catch
            {
                // Ignore filesystem errors
            }

            return null;
        }
    }
}
