using System.Collections.Generic;
using System.Text.Json;

namespace Rook.UI.Web
{
    /// <summary>All live web surfaces, for substrate-wide diagnostics and
    /// operator repair. Weak registration is unnecessary: surfaces
    /// deterministically deregister in Dispose.</summary>
    internal static class WebSurfacePresentationRegistry
    {
        private static readonly object s_lock = new();
        private static readonly List<RookWebSurface> s_surfaces = new();

        public static void Register(RookWebSurface surface)
        { lock (s_lock) { if (!s_surfaces.Contains(surface)) s_surfaces.Add(surface); } }

        public static void Deregister(RookWebSurface surface)
        { lock (s_lock) { s_surfaces.Remove(surface); } }

        public static string DumpAll()
        {
            lock (s_lock)
            {
                var dump = new List<object>();
                foreach (var s in s_surfaces)
                    dump.Add(new
                    {
                        surfaceId = s.SurfaceId,
                        disposed = s.IsDisposed,
                        entries = s.GetHostPresentationDiagnosticEntries()
                    });
                return JsonSerializer.Serialize(dump,
                    new JsonSerializerOptions { WriteIndented = true });
            }
        }

        /// <summary>
        /// Fire-and-forget: schedules an async forced repair per surface on
        /// the UI thread and returns immediately. NEVER blocks on the gapped
        /// toggle (200ms gap) — outcomes land in each surface's diagnostics
        /// ring and are read via a follow-up DumpAll().
        /// </summary>
        public static string ScheduleRepairAll(string reason)
        {
            RookWebSurface[] snapshot;
            lock (s_lock) { snapshot = s_surfaces.ToArray(); }
            foreach (var s in snapshot)
                s.SchedulePresentationRepair(reason);
            return "scheduled:" + snapshot.Length;
        }
    }
}
