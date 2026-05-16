using System;
using System.Globalization;
using System.IO;

namespace Rook.UI.Panels
{
    internal static class HostedPanelLifecycleTrace
    {
        private const long MaxBytes = 512 * 1024;
        private const string FileName = "panel-lifecycle.log";

        public static bool IsEnabled()
        {
            return string.Equals(
                Environment.GetEnvironmentVariable("ROOK_PANEL_LIFECYCLE_TRACE"),
                "1",
                StringComparison.Ordinal);
        }

        public static void Record(
            string panelType,
            uint documentSerial,
            string surfaceId,
            string eventName,
            PanelLifecycleFacts facts,
            HostedSurfaceDecision decision,
            string detail = "")
        {
            if (!IsEnabled())
            {
                return;
            }

            try
            {
                var logDir = GetLogDirectory();
                Directory.CreateDirectory(logDir);
                var path = Path.Combine(logDir, FileName);
                RotateIfNeeded(path);
                var line =
                    DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture) +
                    "\tpanel=" + Sanitize(panelType) +
                    "\tdoc=" + documentSerial.ToString(CultureInfo.InvariantCulture) +
                    "\tsurface=" + Sanitize(surfaceId) +
                    "\tevent=" + Sanitize(eventName) +
                    "\treason=" + facts.LastReason +
                    "\treportedVisible=" + facts.PanelReportedVisible +
                    "\tselectedTab=" + facts.IsSelectedTab +
                    "\trhinoSelectedVisible=" + facts.IsRhinoSelectedPanelVisible +
                    "\thostReady=" + facts.IsHostReady +
                    "\tclosing=" + facts.IsClosing +
                    "\tdeferAttempt=" + facts.DeferAttempt.ToString(CultureInfo.InvariantCulture) +
                    "\taction=" + decision.Action +
                    "\tdecisionReason=" + Sanitize(decision.Reason) +
                    "\tdetail=" + Sanitize(detail) +
                    Environment.NewLine;
                File.AppendAllText(path, line);
            }
            catch
            {
                // Diagnostics must never affect panel behavior.
            }
        }

        private static string GetLogDirectory()
        {
            var root = Environment.GetEnvironmentVariable("ROOK_DATA_DIR");
            if (string.IsNullOrWhiteSpace(root))
            {
                root = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "Rook");
            }

            return Path.Combine(root, "logs");
        }

        private static void RotateIfNeeded(string path)
        {
            var info = new FileInfo(path);
            if (!info.Exists || info.Length < MaxBytes)
            {
                return;
            }

            var rotated = path + ".1";
            if (File.Exists(rotated))
            {
                File.Delete(rotated);
            }

            File.Move(path, rotated);
        }

        private static string Sanitize(string value)
        {
            return value
                .Replace('\t', ' ')
                .Replace('\r', ' ')
                .Replace('\n', ' ');
        }
    }
}
