using Rook.UI.Web;
using Xunit;

namespace Rook.Tests.UI.Web
{
    public class PresentationProbeReportTests
    {
        // ExecuteScriptAsync wraps the JSON.stringify result in ANOTHER layer
        // of JSON string encoding: "\"{\\\"visibilityState\\\":...}\""
        private static string Wrap(string inner) =>
            System.Text.Json.JsonSerializer.Serialize(inner);

        [Fact]
        public void Visible_ParsesHealthy()
        {
            var raw = Wrap("{\"visibilityState\":\"visible\",\"hidden\":false,\"readyState\":\"complete\",\"hasRoot\":true,\"viewport\":[100,50],\"appRect\":null}");
            var report = PresentationProbeReport.Parse(raw);
            Assert.Equal(ProbeOutcome.Healthy, report.Outcome);
        }

        [Fact]
        public void Hidden_ParsesRendererHidden()
        {
            var raw = Wrap("{\"visibilityState\":\"hidden\",\"hidden\":true,\"readyState\":\"complete\",\"hasRoot\":true,\"viewport\":[100,50],\"appRect\":null}");
            Assert.Equal(ProbeOutcome.RendererHidden, PresentationProbeReport.Parse(raw).Outcome);
        }

        [Fact]
        public void SingleEncoded_StillParses()
        {
            // Defensive: some hosts hand back the inner JSON directly.
            var raw = "{\"visibilityState\":\"visible\"}";
            Assert.Equal(ProbeOutcome.Healthy, PresentationProbeReport.Parse(raw).Outcome);
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("null")]
        [InlineData("\"null\"")]
        [InlineData("not json at all")]
        [InlineData("\"{\\\"visibilityState\\\":42}\"")]
        public void Malformed_IsProbeInvalid(string raw)
        {
            Assert.Equal(ProbeOutcome.ProbeInvalid, PresentationProbeReport.Parse(raw).Outcome);
        }

        [Fact]
        public void RawPayloadPreservedForDiagnostics()
        {
            var raw = Wrap("{\"visibilityState\":\"hidden\"}");
            Assert.Contains("hidden", PresentationProbeReport.Parse(raw).PayloadJson);
        }
    }
}
