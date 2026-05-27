using Rhino;
using Rhino.Commands;
using Rook.UI.Vision;

namespace Rook.Commands
{
    /// <summary>
    /// Dumps bounded in-memory Vision presentation diagnostics for live
    /// validation. This command does not write files or affect recovery.
    /// </summary>
    public class RookDumpVisionPresentationStateCommand : Command
    {
        public override string EnglishName => "RookDumpVisionPresentationState";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            _ = doc;
            _ = mode;
            RhinoApp.WriteLine("Rook Vision presentation diagnostics:");
            RhinoApp.WriteLine(RookVisionPanel.DumpPresentationDiagnostics());
            return Result.Success;
        }
    }
}
