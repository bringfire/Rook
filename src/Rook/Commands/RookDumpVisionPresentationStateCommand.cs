using System;
using System.IO;
using Rhino;
using Rhino.Commands;
using Rhino.Input;
using Rhino.Input.Custom;
using Rook.UI.Web;

namespace Rook.Commands
{
    /// <summary>
    /// Dumps bounded in-memory presentation diagnostics for ALL live web
    /// surfaces (Vision, Chat, Knowledge Graph, …) for live validation.
    /// The full dump is written to a temp file and the path printed to
    /// the Rhino command line.
    ///
    /// The <c>Repair</c> toggle (default No) additionally schedules an
    /// operator-forced presentation repair on every live surface.
    /// Repair is accepted-and-scheduled: the command returns immediately
    /// and outcomes land in each surface's diagnostics ring — run the
    /// command again to see them in the dump.
    /// </summary>
    public class RookDumpVisionPresentationStateCommand : Command
    {
        public override string EnglishName => "RookDumpVisionPresentationState";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            _ = doc;

            var repair = false;
            using (var go = new GetOption())
            {
                go.SetCommandPrompt("Dump web panel presentation state");
                go.AcceptNothing(true);
                var repairToggle = new OptionToggle(false, "No", "Yes");
                go.AddOptionToggle("Repair", ref repairToggle);

                while (true)
                {
                    var res = go.Get();
                    if (res == GetResult.Option)
                        continue;
                    if (res == GetResult.Cancel)
                        return Result.Cancel;
                    break;
                }

                repair = repairToggle.CurrentValue;
            }

            var dump = WebSurfacePresentationRegistry.DumpAll();
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
                RhinoApp.WriteLine("Rook web panel presentation diagnostics written to:");
                RhinoApp.WriteLine(path);
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine("Rook web panel presentation diagnostics file write failed:");
                RhinoApp.WriteLine(ex.GetType().Name + ": " + ex.Message);
            }

            if (repair)
            {
                var scheduled = WebSurfacePresentationRegistry.ScheduleRepairAll(
                    "command-repair");
                var count = scheduled.StartsWith("scheduled:", StringComparison.Ordinal)
                    ? scheduled.Substring("scheduled:".Length)
                    : scheduled;
                RhinoApp.WriteLine(
                    $"repair scheduled ({count} surfaces) — run the command again " +
                    "to see outcomes in the dump");
            }

            return Result.Success;
        }
    }
}
