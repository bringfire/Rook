using System.Collections.Generic;
using System.Text.Json;
using Rook.Handlers;
using Xunit;

namespace Rook.Tests.Handlers
{
    /// <summary>
    /// Pure-helper tests for <see cref="ViewportHandler"/>. Coverage is
    /// intentionally narrow: timeout/dimension/scale clamping, raytraced
    /// mode name recognition, and request-shape validation. Anything that
    /// needs <c>RhinoDoc.ActiveDoc</c>, <c>DisplayModeDescription.GetDisplayModes</c>,
    /// or <c>view.CaptureToBitmap</c> is covered by the live-Rhino smoke
    /// checklist in the PR body, not here.
    /// </summary>
    public class ViewportHandlerTests
    {
        // ─── ClampRaytracedTimeoutMs ───────────────────────────────────

        [Fact]
        public void ClampRaytracedTimeoutMs_Null_ReturnsDefault()
        {
            Assert.Equal(
                ViewportHandler.DefaultRaytracedTimeoutMs,
                ViewportHandler.ClampRaytracedTimeoutMs(null));
        }

        [Theory]
        [InlineData(0)]
        [InlineData(-1)]
        [InlineData(-5000)]
        public void ClampRaytracedTimeoutMs_NonPositive_ReturnsDefault(int raw)
        {
            Assert.Equal(
                ViewportHandler.DefaultRaytracedTimeoutMs,
                ViewportHandler.ClampRaytracedTimeoutMs(raw));
        }

        [Theory]
        [InlineData(1)]
        [InlineData(5000)]
        [InlineData(10000)]
        [InlineData(15000)]
        [InlineData(20000)]
        public void ClampRaytracedTimeoutMs_WithinRange_ReturnsRaw(int raw)
        {
            Assert.Equal(raw, ViewportHandler.ClampRaytracedTimeoutMs(raw));
        }

        [Theory]
        [InlineData(20001)]
        [InlineData(25000)]
        [InlineData(30000)]
        [InlineData(60000)]
        public void ClampRaytracedTimeoutMs_AboveCap_ClampsToMax(int raw)
        {
            // The 20 s cap leaves headroom under the bridge's 30 s ceiling
            // in NativeGhBridgeRegistrar.ExecuteApiResponseCallback.
            Assert.Equal(
                ViewportHandler.MaxRaytracedTimeoutMs,
                ViewportHandler.ClampRaytracedTimeoutMs(raw));
        }

        [Fact]
        public void MaxRaytracedTimeoutMs_LeavesHeadroomUnderBridgeCeiling()
        {
            // The bridge waitHandle times out at 30 s. Public cap must
            // leave room for capture + PNG write + JSON marshal.
            Assert.True(ViewportHandler.MaxRaytracedTimeoutMs <= 20000);
            Assert.True(ViewportHandler.MaxRaytracedTimeoutMs < 30000);
        }

        // ─── ClampDimension / ClampScale ───────────────────────────────

        [Fact]
        public void ClampDimension_Null_ReturnsDefault()
        {
            Assert.Equal(1024, ViewportHandler.ClampDimension(null, 1024));
        }

        [Theory]
        [InlineData(0, 100)]
        [InlineData(-50, 100)]
        [InlineData(50, 100)]
        [InlineData(99, 100)]
        public void ClampDimension_BelowMin_ClampsToMin(int raw, int expected)
        {
            Assert.Equal(expected, ViewportHandler.ClampDimension(raw, 800));
        }

        [Theory]
        [InlineData(4001, 4000)]
        [InlineData(8000, 4000)]
        [InlineData(16000, 4000)]
        public void ClampDimension_AboveMax_ClampsToMax(int raw, int expected)
        {
            Assert.Equal(expected, ViewportHandler.ClampDimension(raw, 800));
        }

        [Theory]
        [InlineData(100)]
        [InlineData(800)]
        [InlineData(1024)]
        [InlineData(1920)]
        [InlineData(4000)]
        public void ClampDimension_InRange_ReturnsRaw(int raw)
        {
            Assert.Equal(raw, ViewportHandler.ClampDimension(raw, 800));
        }

        // ─── IsRaytracedModeName ───────────────────────────────────────

        [Theory]
        [InlineData("raytraced")]
        [InlineData("Raytraced")]
        [InlineData("RAYTRACED")]
        [InlineData("cycles")]
        [InlineData("Cycles")]
        public void IsRaytracedModeName_MatchesKnownNames(string name)
        {
            Assert.True(ViewportHandler.IsRaytracedModeName(name));
        }

        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("Shaded")]
        [InlineData("Rendered")]
        [InlineData("Wireframe")]
        [InlineData("ray traced")]  // space breaks the match
        [InlineData("rayTraced ")] // trailing whitespace breaks the match
        public void IsRaytracedModeName_RejectsOthers(string? name)
        {
            Assert.False(ViewportHandler.IsRaytracedModeName(name));
        }

        // ─── ParseRequest ──────────────────────────────────────────────

        [Fact]
        public void ParseRequest_NullBody_ReturnsDefaults()
        {
            var r = ViewportHandler.ParseRequest(null);
            Assert.Equal(ViewportHandler.DefaultWidth, r.Width);
            Assert.Equal(ViewportHandler.DefaultHeight, r.Height);
            Assert.Equal(ViewportHandler.DefaultRaytracedTimeoutMs, r.RaytracedTimeoutMs);
            Assert.False(r.RaytracedConverge);
            Assert.Null(r.DisplayMode);
            Assert.Null(r.ViewName);
            Assert.False(r.HasExplicitWidth);
            Assert.False(r.HasExplicitHeight);
        }

        [Fact]
        public void ParseRequest_Tier3Backend_Accepted()
        {
            var body = JsonSerializer.Serialize(new
            {
                captureBackend = "tier3",
                width = 1024,
                height = 1024,
                displayMode = "Raytraced",
                raytracedConverge = true,
                raytracedTimeoutMs = 15000,
            });
            var r = ViewportHandler.ParseRequest(body);
            Assert.Equal(1024, r.Width);
            Assert.Equal(1024, r.Height);
            Assert.True(r.HasExplicitWidth);
            Assert.True(r.HasExplicitHeight);
            Assert.Equal("Raytraced", r.DisplayMode);
            Assert.True(r.RaytracedConverge);
            Assert.Equal(15000, r.RaytracedTimeoutMs);
        }

        [Fact]
        public void ParseRequest_ViewId_Accepted()
        {
            var body = JsonSerializer.Serialize(new
            {
                captureBackend = "tier3",
                viewId = "12345",
            });
            var r = ViewportHandler.ParseRequest(body);
            Assert.Equal("12345", r.ViewId);
        }

        [Fact]
        public void ParseRequest_EmptyBackendField_Accepted()
        {
            // Absent (no field) and empty string are both legal at this
            // layer — the native branch already filtered non-tier3 values.
            var body = JsonSerializer.Serialize(new { width = 800 });
            var r = ViewportHandler.ParseRequest(body);
            Assert.Equal(800, r.Width);
        }

        [Theory]
        [InlineData("legacy")]
        [InlineData("Tier3")]   // case matters — native enforces lowercase
        [InlineData("TIER3")]
        [InlineData("sdk")]
        [InlineData("bogus")]
        public void ParseRequest_NonTier3Backend_Throws(string backend)
        {
            var body = JsonSerializer.Serialize(new { captureBackend = backend });
            var ex = Assert.Throws<System.ArgumentException>(
                () => ViewportHandler.ParseRequest(body));
            Assert.Contains("captureBackend", ex.Message);
        }

        [Fact]
        public void ParseRequest_MalformedJson_Throws()
        {
            Assert.Throws<System.ArgumentException>(
                () => ViewportHandler.ParseRequest("{not-json"));
        }

        [Fact]
        public void ParseRequest_TimeoutAboveCap_ClampedInResult()
        {
            var body = JsonSerializer.Serialize(new
            {
                captureBackend = "tier3",
                raytracedTimeoutMs = 60000,
            });
            var r = ViewportHandler.ParseRequest(body);
            Assert.Equal(ViewportHandler.MaxRaytracedTimeoutMs, r.RaytracedTimeoutMs);
        }

        // ─── Unsupported-field rejection ───────────────────────────────
        // Legacy /viewport honors scale, transparentBackground, drawGrid,
        // drawWorldAxes, drawCPlaneAxes via _-ViewCaptureToFile. Tier 3
        // does not map these yet. Accepting-and-ignoring would produce
        // false-success responses; we hard-reject on presence so the caller
        // knows their flags are not being honored.

        [Theory]
        [InlineData("scale")]
        [InlineData("transparentBackground")]
        [InlineData("drawGrid")]
        [InlineData("drawWorldAxes")]
        [InlineData("drawCPlaneAxes")]
        public void ParseRequest_UnsupportedLegacyField_Rejected(string field)
        {
            // Present with a plausible legacy value should throw.
            var payload = new Dictionary<string, object?>
            {
                ["captureBackend"] = "tier3",
                [field] = field == "scale" ? 2 : (object)true,
            };
            var body = JsonSerializer.Serialize(payload);
            var ex = Assert.Throws<System.ArgumentException>(
                () => ViewportHandler.ParseRequest(body));
            Assert.Contains(field, ex.Message);
            Assert.Contains("Tier 3", ex.Message);
        }

        [Fact]
        public void ParseRequest_MultipleUnsupportedFields_AllListedInError()
        {
            var body = JsonSerializer.Serialize(new
            {
                captureBackend = "tier3",
                scale = 2,
                drawGrid = true,
                transparentBackground = false,
            });
            var ex = Assert.Throws<System.ArgumentException>(
                () => ViewportHandler.ParseRequest(body));
            Assert.Contains("scale", ex.Message);
            Assert.Contains("drawGrid", ex.Message);
            // Explicit false is still "present" — the caller opted in to
            // the field and expects it to influence capture.
            Assert.Contains("transparentBackground", ex.Message);
        }

        [Fact]
        public void UnsupportedLegacyFields_ContractListIsExhaustive()
        {
            // Anchors the rejection set so a future parity PR that removes
            // entries here forces a review of whether ViewCaptureSettings
            // has actually been wired up for that field.
            Assert.Equal(
                new[]
                {
                    "scale",
                    "transparentBackground",
                    "drawGrid",
                    "drawWorldAxes",
                    "drawCPlaneAxes",
                },
                ViewportHandler.UnsupportedLegacyFields);
        }
    }
}
