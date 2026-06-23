using System.IO;
using System.Reflection;
using Rook.UI.Vision;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    /// <summary>
    /// Source-assertion tests for Task 1 of the Reconstruct UI scaffold:
    /// mode switcher (T3D | I3D | MV3D), prompt panel, and data-mode gating.
    /// All assertions are structural checks against the embedded HTML/JS/CSS
    /// resources — no WebView2 or runtime wiring is exercised here.
    /// </summary>
    public class ReconstructScaffoldSourceTests
    {
        // ─── HTML assertions ──────────────────────────────────────────

        [Fact]
        public void IndexHtml_ReconstructModeSwitcher_HasThreeModesWithExactTooltips()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-mode-radios\"", html);
            Assert.Contains("data-mode=\"t3d\"", html);
            Assert.Contains("data-mode=\"i3d\"", html);
            Assert.Contains("data-mode=\"mv3d\"", html);
            Assert.Contains("title=\"Text to 3D: generate a model from a text prompt.\"", html);
            Assert.Contains("title=\"Image to 3D: reconstruct from one source image.\"", html);
            Assert.Contains("title=\"Multi-view 3D: reconstruct from labeled front/side/back images.\"", html);
        }

        [Fact]
        public void IndexHtml_ReconstructPrompt_Present()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-prompt\"", html);
            Assert.Contains("id=\"reconstruct-prompt-hint\"", html);
        }

        // ─── app.js assertions ────────────────────────────────────────

        [Fact]
        public void AppJs_ReconstructModeGating_DefaultsToI3d()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("re.modeSwitch = $(\"reconstruct-mode-radios\");", js);
            Assert.Contains("function setReconstructMode(", js);
            Assert.Contains("let reconstructMode = \"i3d\";", js);
        }

        // ─── Task 2 assertions ────────────────────────────────────────

        [Fact]
        public void IndexHtml_FrontPane_HasSingleClearAndReusesChooseSourceAsPick()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-choose-source\"", html);   // repurposed to Pick
            Assert.Contains("id=\"reconstruct-source-clear\"", html);     // new
            Assert.DoesNotContain("id=\"reconstruct-source-pick\"", html); // no competing control
        }

        [Fact]
        public void IndexHtml_ReconstructPickerModal_Present()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-picker-modal\"", html);
            Assert.Contains("id=\"reconstruct-picker-grid\"", html);
            Assert.Contains("id=\"reconstruct-picker-close\"", html);
        }

        [Fact]
        public void AppJs_SlotStateCarriesRenderFields_AndSendTo3dLandsInFront()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("function fillSlot(", js);
            Assert.Contains("function clearSlot(", js);
            Assert.Contains("previewSrc:", js);
            // Send-to-3D invariant: presetSource populates slots.front and large pane
            var s = js.IndexOf("function presetSource(", System.StringComparison.Ordinal);
            var e = js.IndexOf("return {", s, System.StringComparison.Ordinal);
            var body = js.Substring(s, e - s);
            Assert.Contains("fillSlot(\"front\"", body);
            Assert.Contains("if (reconstructMode === \"t3d\") setReconstructMode(\"i3d\");", body);
        }

        // ─── Task 3 assertions ────────────────────────────────────────

        [Fact]
        public void IndexHtml_Mv3dSlots_PresentWithDataSlots()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-mv-slots\"", html);
            foreach (var s in new[] { "left","right","back","top","three_quarter" })
                Assert.Contains($"data-slot=\"{s}\"", html);
            Assert.Contains("reconstruct-slot-optional", html); // top/¾ marked optional
        }

        [Fact]
        public void AppJs_Mv3dSlots_WiredByDataSlot()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("re.mvSlots = $(\"reconstruct-mv-slots\");", js);
            Assert.Contains("re.mvSlots.querySelectorAll(\"[data-slot]\")", js);
            Assert.Contains("openReconstructPicker(", js);
        }

        // ─── helpers ──────────────────────────────────────────────────

        private static string ReadVisionResource(string fileName)
        {
            var asm = typeof(VisionWebSurface).Assembly;
            var resourceName = "Rook.UI.Vision.Resources." + fileName;
            using var stream = asm.GetManifestResourceStream(resourceName);
            Assert.NotNull(stream);
            using var reader = new StreamReader(stream!);
            return reader.ReadToEnd();
        }

        private static int CountOccurrences(string haystack, string needle)
        {
            int count = 0;
            int index = 0;
            while ((index = haystack.IndexOf(needle, index, System.StringComparison.Ordinal)) >= 0)
            {
                count++;
                index += needle.Length;
            }
            return count;
        }
    }
}
