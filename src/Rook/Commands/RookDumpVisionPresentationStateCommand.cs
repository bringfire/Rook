using System;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Threading;
using Rhino;
using Rhino.Commands;
using Rook.UI.Vision;

namespace Rook.Commands
{
    public class RookDumpVisionPresentationStateCommand : Command
    {
        public override string EnglishName => "RookDumpVisionPresentationState";

        protected override Result RunCommand(RhinoDoc doc, RunMode mode)
        {
            try
            {
                var snapshot = VisionWebSurface.PresentationState.Snapshot();
                var payload = VisionPresentationStateDump.CreatePayload(
                    snapshot,
                    GetRookVersion(),
                    RhinoApp.ExeVersion.ToString(),
                    Process.GetCurrentProcess().Id,
                    Thread.CurrentThread.ManagedThreadId);

                var dumpDirectory = Path.Combine(Path.GetTempPath(), "rook");
                Directory.CreateDirectory(dumpDirectory);

                var fileName = "vision-presentation-state-"
                    + snapshot.DumpRequestedUtc.UtcDateTime.ToString("yyyyMMdd-HHmmss-fff")
                    + ".json";
                var path = Path.Combine(dumpDirectory, fileName);
                var json = JsonSerializer.Serialize(
                    payload,
                    VisionPresentationStateDump.JsonOptions);

                File.WriteAllText(path, json);
                RhinoApp.WriteLine("Rook vision presentation state dumped to: " + path);
                return Result.Success;
            }
            catch (Exception ex)
            {
                RhinoApp.WriteLine("Rook vision presentation state dump failed: " + ex.Message);
                return Result.Failure;
            }
        }

        private static string GetRookVersion()
            => typeof(RookPlugin).Assembly.GetName().Version?.ToString() ?? string.Empty;
    }
}
