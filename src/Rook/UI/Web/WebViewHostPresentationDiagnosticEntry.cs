using System;

namespace Rook.UI.Web
{
    /// <summary>
    /// Bounded in-memory diagnostics ring entry. Populated exclusively by
    /// the presentation reconciler's Record path: the event name lands in
    /// <c>Reason</c> and the detail/probe payload in <c>ActionResult</c>.
    /// </summary>
    internal sealed record WebViewHostPresentationDiagnosticEntry
    {
        public int Sequence { get; init; }
        public DateTimeOffset TimestampUtc { get; init; }
        public string Surface { get; init; } = string.Empty;
        public string Reason { get; init; } = string.Empty;
        public string ActionResult { get; init; } = string.Empty;
    }
}
