using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using Rook.Services.Vision;
using Rook.Services.Vision.Fal.Models;

namespace Rook.Vision.Qualification
{
    internal static class CatalogQualification
    {
        internal static int Validate(string catalogDirectory, string reportPath)
        {
            string root = Path.GetFullPath(catalogDirectory).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
            string report = Path.GetFullPath(reportPath);
            if (report.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Write the qualification report outside the catalog root.");
            // --root is the catalog itself, not the assembly directory accepted by FalCatalogLoader.
            var result = new FalCatalogCompiler().Compile(root, VisionProviderRegistrations.GetLegacyModelIds());
            var diagnostics = result.Diagnostics.Select(d => new { file = d.File, pointer = d.Pointer, message = d.Message }).ToList();
            var files = new List<object>();
            if (result.Catalog != null)
            {
                try
                {
                    foreach (string file in JsonFiles(root).OrderBy(p => p, StringComparer.OrdinalIgnoreCase))
                    {
                        using var sha = SHA256.Create();
                        using var input = File.OpenRead(file);
                        files.Add(new { path = file.Substring(root.Length + 1).Replace('\\', '/'), sha256 = BitConverter.ToString(sha.ComputeHash(input)).Replace("-", "") });
                    }
                }
                catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException)
                { diagnostics.Add(new { file = root, pointer = "/", message = ex.Message }); }
            }
            bool success = result.Catalog != null && diagnostics.Count == 0;
            var definitions = result.Catalog?.Definitions.Select(d => new {
                model_id = d.ModelId, definition_id = d.DefinitionId, revision = d.Revision,
                definition_hash = d.DefinitionHash, source_file = d.SourceFile
            }).ToArray();
            Directory.CreateDirectory(Path.GetDirectoryName(report)!);
            File.WriteAllText(report, JsonSerializer.Serialize(new {
                schema_version = 1, success, root, diagnostics, files, definitions
            }, new JsonSerializerOptions { WriteIndented = true }));
            foreach (var diagnostic in diagnostics) Console.Error.WriteLine(diagnostic.file + " " + diagnostic.pointer + ": " + diagnostic.message);
            Console.WriteLine((success ? "PASS" : "FAIL") + ": catalog " + root + "; report " + report);
            return success ? 0 : 1;
        }

        private static IEnumerable<string> JsonFiles(string directory)
        {
            if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0) throw new IOException("Catalog contains a reparse directory: " + directory);
            foreach (string entry in Directory.EnumerateFileSystemEntries(directory))
            {
                var attributes = File.GetAttributes(entry);
                if ((attributes & FileAttributes.ReparsePoint) != 0) throw new IOException("Catalog contains a reparse entry: " + entry);
                if ((attributes & FileAttributes.Directory) != 0) { foreach (string file in JsonFiles(entry)) yield return file; }
                else if (string.Equals(Path.GetExtension(entry), ".json", StringComparison.OrdinalIgnoreCase)) yield return entry;
            }
        }
    }
}
