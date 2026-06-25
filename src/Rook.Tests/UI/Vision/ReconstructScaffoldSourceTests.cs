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
        public void AppJs_ReconstructPicker_RendersLoadingEmptyAndFailureStates()
        {
            var js = ReadVisionResource("app.js");
            var s = js.IndexOf("async function openReconstructPicker(", System.StringComparison.Ordinal);
            Assert.True(s >= 0, "openReconstructPicker() not found");
            var e = js.IndexOf("function closeReconstructPicker(", s, System.StringComparison.Ordinal);
            Assert.True(e > s, "closeReconstructPicker() boundary not found after openReconstructPicker()");
            var body = js.Substring(s, e - s);

            Assert.Contains("Loading", body);
            Assert.Contains("No images yet", body);
            Assert.Contains("Failed to load images", body);
            Assert.Contains("re.pickerModal.classList.remove(\"hidden\");", body);
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
            // Fal Pro vocabulary: bottom/left_front/right_front replace three_quarter.
            foreach (var s in new[] { "left","right","back","top","bottom","left_front","right_front" })
                Assert.Contains($"data-slot=\"{s}\"", html);
            Assert.DoesNotContain("data-slot=\"three_quarter\"", html);
            Assert.Contains("reconstruct-slot-optional", html); // top + secondary slots marked optional
        }

        [Fact]
        public void AppJs_Mv3dSlots_WiredByDataSlot()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("re.mvSlots = $(\"reconstruct-mv-slots\");", js);
            Assert.Contains("re.mvSlots.querySelectorAll(\"[data-slot]\")", js);
            Assert.Contains("openReconstructPicker(", js);
        }

        // ─── Task 4 assertions ────────────────────────────────────────

        [Fact]
        public void IndexHtml_ActionNote_Present()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-action-note\"", html);
        }

        [Fact]
        public void AppJs_ModeDrivenActionAndModelPlaceholder()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("function updateReconstructActionForMode", js);
            Assert.Contains("Text-to-3D arrives when a provider lands.", js);
            Assert.Contains("No models available for this mode yet", js);   // t3d / empty mv3d picker
        }

        [Fact]
        public void AppJs_Mv3dSubmits_ViewsArray_AndDropsThreeQuarterState()
        {
            var js = ReadVisionResource("app.js");
            // slot-state object uses the Fal vocabulary
            Assert.Contains("left_front", js);
            Assert.Contains("right_front", js);
            Assert.DoesNotContain("three_quarter", js);
            // submit carries a views[] array
            Assert.Contains("views:", js);
            // MV3D action is no longer the disabled "Assemble view set" stub
            Assert.DoesNotContain("Slot assembly wires next.", js);
            Assert.DoesNotContain("Assemble view set", js);
            // MV3D picker filters to multi-view-capable models
            Assert.Contains("supports_multi_view", js);
        }

        // ─── Pro options (Slice 2) assertions ─────────────────────────

        [Fact]
        public void IndexHtml_ReconstructOptions_ExposeGenerateTypePbrFaceCount()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-options\"", html);
            Assert.Contains("id=\"reconstruct-opt-generate-type\"", html);
            Assert.Contains("id=\"reconstruct-opt-enable-pbr\"", html);
            Assert.Contains("id=\"reconstruct-opt-face-count\"", html);
        }

        [Fact]
        public void AppJs_SubmitViewsBuilder_IsModeAware()
        {
            // Secondary slots must only leave the submit builder in MV3D with a multi-view-capable
            // model — otherwise stale MV3D slots leak into a later I3D/single-image submit.
            var js = ReadVisionResource("app.js");
            var s = js.IndexOf("async function submit(", System.StringComparison.Ordinal);
            Assert.True(s >= 0, "submit() not found");
            var e = js.IndexOf("async function poll(", s, System.StringComparison.Ordinal);
            Assert.True(e > s, "poll() boundary not found after submit()");
            var body = js.Substring(s, e - s);
            Assert.Contains("reconstructMode === \"mv3d\"", body);
            Assert.Contains("supports_multi_view", body);
            Assert.Contains("views:", body);
        }

        [Fact]
        public void OutputControl_HiddenForCatalogOptionModels()
        {
            // For catalog-option models (Pro), Generate Type is the real Fal control; the legacy
            // textured/geometry Output segmented control must be hidden so it can't silently disagree.
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-output-field\"", html);
            var js = ReadVisionResource("app.js");
            Assert.Contains("re.outputField = $(\"reconstruct-output-field\");", js);
            Assert.Contains("re.outputField.classList", js);   // toggled in renderModelOptions
        }

        [Fact]
        public void AppJs_RendersCatalogOptions_AndGatesPbrUnderGeometry()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("reconstruct-opt-generate-type", js);
            Assert.Contains("reconstruct-opt-enable-pbr", js);
            Assert.Contains("reconstruct-opt-face-count", js);
            Assert.Contains("renderModelOptions", js);
            Assert.Contains("Geometry", js);
            Assert.Contains("generate_type", js);
            Assert.Contains("face_count", js);
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
