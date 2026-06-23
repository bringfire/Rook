using System.IO;
using Rook.UI.Vision;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    /// <summary>
    /// Source-assertion (panel-dark regression) tests for the Studio
    /// image-processing slice: Pick-from-Gallery picker, operation-aware
    /// result panel, Remove Background operation, and Gallery eligibility
    /// for preprocessed_image. Structural checks against embedded
    /// HTML/JS/CSS resources — no WebView2 runtime is exercised.
    /// </summary>
    public class StudioImageProcessingSourceTests
    {
        // ─── Task 2: Pick from Gallery ────────────────────────────────

        [Fact]
        public void IndexHtml_PickFromGallery_ControlAndModalPresent()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"studio-pick-gallery-btn\"", html);
            Assert.Contains("id=\"studio-picker-modal\"", html);
            Assert.Contains("id=\"studio-picker-grid\"", html);
            Assert.Contains("id=\"studio-picker-close\"", html);
        }

        [Fact]
        public void AppJs_StudioPicker_CachesIdsAndListsFourKinds()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("el.studioPickGalleryBtn = $(\"studio-pick-gallery-btn\");", js);
            Assert.Contains("el.studioPickerModal = $(\"studio-picker-modal\");", js);
            Assert.Contains("el.studioPickerGrid = $(\"studio-picker-grid\");", js);
            Assert.Contains("el.studioPickerClose = $(\"studio-picker-close\");", js);
            Assert.Contains("function openStudioPicker(", js);
            Assert.Contains("function selectStudioPickerArtifact(", js);
            // The four agreed image kinds.
            Assert.Contains("\"generated_image\", \"imported_image\", \"captured_viewport\", \"preprocessed_image\"", js);
            // Picker selection routes through the existing Studio source path.
            Assert.Contains("applyStudioSource({", js);
        }

        // ─── Task 3: Operation-aware result panel ─────────────────────

        [Fact]
        public void IndexHtml_ResultPanel_HasTitleIdAndSplitActionGroups()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"studio-result-title\"", html);
            Assert.Contains("id=\"studio-result-gen-actions\"", html);
            Assert.Contains("id=\"studio-result-op-actions\"", html);
            Assert.Contains("id=\"studio-use-as-source-btn\"", html);
            Assert.Contains("id=\"studio-open-in-gallery-btn\"", html);
            Assert.Contains("id=\"studio-send-to-reconstruct-btn\"", html);
        }

        [Fact]
        public void AppJs_ResultPanel_IsOperationAware()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("el.studioResultTitle = $(\"studio-result-title\");", js);
            Assert.Contains("el.studioResultGenActions = $(\"studio-result-gen-actions\");", js);
            Assert.Contains("el.studioResultOpActions = $(\"studio-result-op-actions\");", js);
            Assert.Contains("function setStudioResultMode(", js);
            // operation-aware copy: background-removed result is titled, not "Generated"
            Assert.Contains("\"Background removed\"", js);
            // generation path explicitly restores generate-mode header/actions
            Assert.Contains("setStudioResultMode(\"generate\")", js);
            // reuse actions exist and route correctly
            Assert.Contains("function studioUseResultAsSource(", js);
            Assert.Contains("function studioOpenResultInGallery(", js);
            Assert.Contains("function studioSendResultToReconstruct(", js);
            Assert.Contains("Reconstruct.presetSource(", js);
            Assert.Contains("openArtifactModal(", js);
        }

        [Fact]
        public void Styles_OpActions_WrapToAvoidOverflow()
        {
            // P2: three reuse buttons must not overflow the non-wrapping result header row.
            var css = ReadVisionResource("styles.css");
            Assert.Contains("#studio-result-op-actions", css);
            Assert.Contains("flex-wrap: wrap", css);
        }

        // ─── Task 4: Operations group + Remove Background ──────────────

        [Fact]
        public void IndexHtml_OperationsGroup_HasRemoveBackground()
        {
            var html = ReadVisionResource("index.html");
            Assert.Contains("id=\"studio-operations\"", html);
            Assert.Contains("id=\"studio-remove-bg-btn\"", html);
            Assert.Contains("id=\"studio-operation-status\"", html);
            // Ships disabled until an artifact-backed source exists.
            Assert.Contains("id=\"studio-remove-bg-btn\" class=\"btn btn-capture\" disabled", html);
        }

        [Fact]
        public void AppJs_RemoveBackground_RoutesAndGatesOnArtifactSource()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("el.studioRemoveBgBtn = $(\"studio-remove-bg-btn\");", js);
            Assert.Contains("el.studioOperationStatus = $(\"studio-operation-status\");", js);
            Assert.Contains("function studioRemoveBackground(", js);
            Assert.Contains("function awaitStudioRemoveBackground(", js);
            Assert.Contains("function updateStudioOperationsEnabled(", js);
            // routes through the reconstruction bridge op (correct call shape)
            Assert.Contains("reconstructionBridgeCall(\"remove_background\", {", js);
            Assert.Contains("reconstructionBridgeCall(\"job_status\", { job_id:", js);
            // artifact-backed gating + exact disabled hint copy
            Assert.Contains("studioSource && studioSource.artifact_id", js);
            Assert.Contains("Load or pick a source image first", js);
            // success drives the operation-aware result panel
            Assert.Contains("setStudioResultMode(\"background_removed\")", js);
            // enablement is recomputed when the source changes
            Assert.Contains("updateStudioOperationsEnabled();", js);
        }

        // ─── Task 5: Gallery listing + reconstruct eligibility ────────

        [Fact]
        public void AppJs_LoadGallery_IncludesPreprocessedImage()
        {
            var js = ReadVisionResource("app.js");
            // loadGallery() fans out a parallel list_artifacts call per kind; it must include preprocessed_image.
            var s = js.IndexOf("async function loadGallery(", System.StringComparison.Ordinal);
            Assert.True(s >= 0, "loadGallery() not found");
            var e = js.IndexOf("async function ", s + 1, System.StringComparison.Ordinal);
            var body = js.Substring(s, (e > s ? e : js.Length) - s);
            Assert.Contains("kind: \"preprocessed_image\"", body);
        }

        [Fact]
        public void AppJs_CanReconstructArtifact_AcceptsPreprocessedImage()
        {
            var js = ReadVisionResource("app.js");
            var s = js.IndexOf("function canReconstructArtifact(", System.StringComparison.Ordinal);
            Assert.True(s >= 0, "canReconstructArtifact() not found");
            var e = js.IndexOf("\n}", s, System.StringComparison.Ordinal);
            var body = js.Substring(s, e - s);
            Assert.Contains("preprocessed_image", body);
        }

        // ─── Task 6: Panel-dark id-integrity guard ────────────────────

        // Every id this slice caches in app.js MUST have a matching element in
        // index.html. A missing id nulls the cache entry and can blank the whole
        // Vision panel at init. This is the panel-dark regression guard.
        [Theory]
        [InlineData("studio-pick-gallery-btn")]
        [InlineData("studio-picker-modal")]
        [InlineData("studio-picker-grid")]
        [InlineData("studio-picker-close")]
        [InlineData("studio-result-title")]
        [InlineData("studio-result-gen-actions")]
        [InlineData("studio-result-op-actions")]
        [InlineData("studio-use-as-source-btn")]
        [InlineData("studio-open-in-gallery-btn")]
        [InlineData("studio-send-to-reconstruct-btn")]
        [InlineData("studio-operations")]
        [InlineData("studio-remove-bg-btn")]
        [InlineData("studio-operation-status")]
        public void EveryCachedStudioId_ExistsInIndexHtml(string id)
        {
            var js = ReadVisionResource("app.js");
            var html = ReadVisionResource("index.html");
            // The id is cached in app.js …
            Assert.Contains($"$(\"{id}\")", js);
            // … and a matching element exists in index.html.
            Assert.Contains($"id=\"{id}\"", html);
        }

        // ─── helper ───────────────────────────────────────────────────

        private static string ReadVisionResource(string fileName)
        {
            var asm = typeof(VisionWebSurface).Assembly;
            var resourceName = "Rook.UI.Vision.Resources." + fileName;
            using var stream = asm.GetManifestResourceStream(resourceName);
            Assert.NotNull(stream);
            using var reader = new StreamReader(stream!);
            return reader.ReadToEnd();
        }
    }
}
