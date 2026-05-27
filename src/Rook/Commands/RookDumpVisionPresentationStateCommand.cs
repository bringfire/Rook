using System;
using System.IO;
using Rhino;
using Rhino.Commands;
using Rook.UI.Vision;

namespace Rook.Commands
{
    /// <summary>
    /// Dumps bounded in-memory Vision presentation diagnostics for live
    /// validation. This command writes the full dump to a temp file and prints
    /// a compact tail summary to the Rhino command line.
    /// </summary>
    public class RookDumpVisionPresentationStateCommand : Command
    {
        public override string EnglishName => "RookDumpVisionPresentationState";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            _ = doc;
            _ = mode;
            var dump = RookVisionPanel.DumpPresentationDiagnostics();
            var path = Path.Combine(
                Path.GetTempPath(),
                "rook-vision-presentation-" +
                    DateTimeOffset.UtcNow.ToString("yyyyMMdd-HHmmss-fffffff") +
                    "-" +
                    Guid.NewGuid().ToString("N") +
                    ".json");
            try
            {
                File.WriteAllText(path, dump);
                RhinoApp.WriteLine("Rook Vision presentation diagnostics written to:");
                RhinoApp.WriteLine(path);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine("Rook Vision presentation diagnostics file write failed:");
                RhinoApp.WriteLine(ex.GetType().Name + ": " + ex.Message);
            }

            RhinoApp.WriteLine("Rook Vision presentation diagnostics tail:");
            RhinoApp.WriteLine(RookVisionPanel.DumpPresentationDiagnosticsSummary(16));
            return Result.Success;
        }
    }
}
