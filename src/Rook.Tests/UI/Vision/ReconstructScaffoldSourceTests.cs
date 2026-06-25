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
        public void IndexHtml_ReconstructExperimentalToggle_Present()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-include-experimental\"", html);
            Assert.Contains("Experimental models", html);
        }

        [Fact]
        public void AppJs_ReconstructExperimentalToggle_LoadsModelsWithIncludeExperimental()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("re.includeExperimental = $(\"reconstruct-include-experimental\");", js);
            Assert.Contains("let includeExperimentalModels = false;", js);
            Assert.Contains("include_experimental: true", js);
            Assert.Contains("loadModels(true)", js);
            Assert.Contains("re.includeExperimental.checked", js);
            Assert.DoesNotContain("await loadModels(true);\r\n    updateReconstructModelForMode(reconstructMode);", js);
            Assert.DoesNotContain("await loadModels(true);\n    updateReconstructModelForMode(reconstructMode);", js);
        }

        [Fact]
        public void AppJs_ModelHint_IncludesNonStableStatus()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("function modelStatusLabel(", js);
            Assert.Contains("model.status !== \"stable\"", js);
            Assert.Contains("statusLabel", js);
        }

        [Fact]
        public void IndexHtml_ReconstructOptions_UsesDynamicOptionsBody()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"reconstruct-options\"", html);
            Assert.Contains("id=\"reconstruct-options-body\"", html);
            Assert.Contains("id=\"reconstruct-options-hint\"", html);
            Assert.DoesNotContain("id=\"reconstruct-opt-generate-type\"", html);
            Assert.DoesNotContain("id=\"reconstruct-opt-enable-pbr\"", html);
            Assert.DoesNotContain("id=\"reconstruct-opt-face-count\"", html);
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
        public void AppJs_RendersCatalogOptions_FromDescriptorMap()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("re.optionsBody = $(\"reconstruct-options-body\");", js);
            Assert.Contains("re.optionsHint = $(\"reconstruct-options-hint\");", js);
            Assert.Contains("re.optionControls = new Map();", js);
            Assert.Contains("function renderOptionControl(", js);
            Assert.Contains("re.optionControls.set(d.key", js);
            Assert.Contains("case \"enum\":", js);
            Assert.Contains("case \"boolean\":", js);
            Assert.Contains("case \"integer\":", js);
            Assert.Contains("case \"string\":", js);
            Assert.Contains("texture_prompt", js);
            Assert.DoesNotContain("re.optGenerateType", js);
            Assert.DoesNotContain("re.optEnablePbr", js);
            Assert.DoesNotContain("re.optFaceCount", js);
        }

        [Fact]
        public void AppJs_SerializesDescriptorOptions_AndPreservesExplicitFalseBooleans()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("function collectOptionValues({ includeIgnored })", js);
            Assert.Contains("control.checked", js);
            Assert.Contains("values[d.key] = control.checked;", js);
            Assert.Contains("Number.isNaN", js);
            Assert.Contains("collectOptionValues({ includeIgnored: false })", js);
            Assert.DoesNotContain("if (re.optEnablePbr.checked) o.enable_pbr = true;", js);
        }

        [Fact]
        public void AppJs_AppliesIgnoredWhenDependencies_WithoutClearingHiddenValues()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("function isOptionIgnored(descriptor, values)", js);
            Assert.Contains("descriptor.ignored_when", js);
            Assert.Contains("function applyOptionDependencies()", js);
            Assert.Contains("entry.row.classList.toggle(\"hidden\", ignored);", js);
            Assert.Contains("entry.control.disabled = ignored;", js);
            Assert.Contains("Texture-specific options are hidden while texturing is off.", js);
            Assert.Contains("PBR is hidden for geometry-only output.", js);
            Assert.DoesNotContain("entry.control.value = \"\";", js);
            Assert.DoesNotContain("entry.control.checked = false;", js);
        }

        [Theory]
        [InlineData("reconstruct-include-experimental")]
        [InlineData("reconstruct-options")]
        [InlineData("reconstruct-options-body")]
        [InlineData("reconstruct-options-hint")]
        public void EveryCachedReconstructOptionsId_ExistsInIndexHtml(string id)
        {
            var js = ReadVisionResource("app.js");
            var html = ReadVisionResource("index.html");
            Assert.Contains($"$(\"{id}\")", js);
            Assert.Contains($"id=\"{id}\"", html);
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
