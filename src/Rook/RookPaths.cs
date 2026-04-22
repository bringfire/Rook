using System;
using System.IO;

namespace Rook
{
    /// <summary>
    /// Shared file-system paths for the Rook companion plugin.
    /// Extracted from RookServer.cs during companion cleanup (Batch 0).
    /// </summary>
    public static class RookPaths
    {
        /// <summary>
        /// Ephemeral instance discovery folder under <c>%TEMP%\rook</c>.
        /// </summary>
        public static string DiscoveryFolder => Path.Combine(Path.GetTempPath(), "rook");

        /// <summary>
        /// Persistent settings root under <c>%APPDATA%\Rook</c>.
        /// Lazily created by <see cref="RookSettingsStore"/> on first write.
        /// </summary>
        public static string SettingsRoot => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Rook");

        /// <summary>
        /// Path to the Rook settings JSON file under <see cref="SettingsRoot"/>.
        /// </summary>
        public static string SettingsFile => Path.Combine(SettingsRoot, "settings.json");

        /// <summary>
        /// Persistent artifact root under <c>%APPDATA%\Rook\artifacts</c>.
        /// Lazily created by <c>ArtifactStore</c> on first write.
        /// </summary>
        public static string ArtifactsRoot => Path.Combine(SettingsRoot, "artifacts");
    }
}
