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
