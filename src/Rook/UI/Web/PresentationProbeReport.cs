using System.Text.Json;

namespace Rook.UI.Web
{
    internal enum ProbeOutcome
    {
        Healthy,
        RendererHidden,
        RendererUnresponsive,
        ProbeInvalid
    }

    internal sealed record PresentationProbeReport(
        ProbeOutcome Outcome,
        string PayloadJson)
    {
        public static PresentationProbeReport Unresponsive(string detail) =>
            new(ProbeOutcome.RendererUnresponsive, detail);

        /// <summary>
        /// Parses an ExecuteScriptAsync result. WebView2 returns the script
        /// result JSON-encoded (a JSON string containing JSON), so this
        /// unquotes one layer when present, then parses the payload.
        /// Anything undecodable is ProbeInvalid, never an exception.
        /// </summary>
        public static PresentationProbeReport Parse(string? raw)
        {
            if (string.IsNullOrWhiteSpace(raw) || raw == "null")
                return new PresentationProbeReport(ProbeOutcome.ProbeInvalid, raw ?? "");

            var payload = raw!;
            try
            {
                // Unwrap the outer JSON-string layer if present.
                if (payload.Length > 0 && payload[0] == '"')
                {
                    var inner = JsonSerializer.Deserialize<string>(payload);
                    if (inner == null)
                        return new PresentationProbeReport(ProbeOutcome.ProbeInvalid, payload);
                    payload = inner;
                }

                using var doc = JsonDocument.Parse(payload);
                if (doc.RootElement.ValueKind != JsonValueKind.Object ||
                    !doc.RootElement.TryGetProperty("visibilityState", out var vis) ||
                    vis.ValueKind != JsonValueKind.String)
                {
                    return new PresentationProbeReport(ProbeOutcome.ProbeInvalid, payload);
                }

                var outcome = vis.GetString() == "visible"
                    ? ProbeOutcome.Healthy
                    : ProbeOutcome.RendererHidden;
                return new PresentationProbeReport(outcome, payload);
            }
            catch (JsonException)
            {
                return new PresentationProbeReport(ProbeOutcome.ProbeInvalid, payload);
            }
        }
    }
}
