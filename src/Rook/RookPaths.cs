using System.IO;

namespace Rook
{
    /// <summary>
    /// Shared file-system paths for the Rook companion plugin.
    /// Extracted from RookServer.cs during companion cleanup (Batch 0).
    /// </summary>
    public static class RookPaths
    {
        public static string DiscoveryFolder => Path.Combine(Path.GetTempPath(), "rook");
    }
}
