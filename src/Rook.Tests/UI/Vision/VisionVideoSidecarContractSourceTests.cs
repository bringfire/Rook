using System;
using System.IO;
using Xunit;

namespace Rook.Tests.UI.Vision
{
    public class VisionVideoSidecarContractSourceTests
    {
        [Fact]
        public void AppJs_FramePickerDefinesGeneratedVideoFrameRolesOnly()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains(
                "const GENERATED_VIDEO_FRAME_PICKER_ROLES = new Set([\"start_frame\", \"end_frame\"]);",
                js);
            Assert.Contains("function isGeneratedVideoFramePickerRole(role)", js);
            Assert.Contains("return GENERATED_VIDEO_FRAME_PICKER_ROLES.has(role);", js);
            Assert.DoesNotContain("GENERATED_VIDEO_FRAME_PICKER_ROLES = new Set([\"poster\"", js);
            Assert.DoesNotContain("GENERATED_VIDEO_FRAME_PICKER_ROLES = new Set([\"video\"", js);
        }

        [Fact]
        public void AppJs_FramePickerBuildsRoleLevelVideoChoices()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("function buildFramePickerChoices(artifact)", js);

            var helper = ExtractFunction(js, "function buildFramePickerChoices(artifact)");

            Assert.Contains("isVideoArtifactKind(artifact.kind)", helper);
            Assert.Contains("isGeneratedVideoFramePickerRole(file.role)", helper);
            Assert.Contains("role: file.role", helper);
            Assert.Contains("thumbRole: file.role", helper);
        }

        [Fact]
        public void AppJs_FramePickerRequestsGeneratedAndImportedMediaArtifacts()
        {
            var js = ReadVisionResource("app.js");
            var openPicker = ExtractFunction(js, "async function openPicker(slot)");

            Assert.Contains(
                "bridgeCall(\"list_artifacts\", { kind: \"generated_video\", limit: 100 })",
                openPicker);
            Assert.Contains(
                "bridgeCall(\"list_artifacts\", { kind: \"imported_image\", limit: 100 })",
                openPicker);
            Assert.Contains(
                "bridgeCall(\"list_artifacts\", { kind: \"imported_video\", limit: 100 })",
                openPicker);
            Assert.Contains("...(vidData.artifacts || [])", openPicker);
            Assert.Contains("...(importedImageData.artifacts || [])", openPicker);
            Assert.Contains("...(importedVideoData.artifacts || [])", openPicker);
            Assert.Contains(".flatMap(buildFramePickerChoices)", openPicker);
            Assert.Contains("choice.artifact.artifact_id", openPicker);
            Assert.Contains("choice.role", openPicker);
        }

        [Fact]
        public void AppJs_FramePickerDoesNotUseDisplayRoleForGeneratedVideoInputs()
        {
            var js = ReadVisionResource("app.js");
            Assert.Contains("function buildFramePickerChoices(artifact)", js);

            var choicesBuilder = ExtractFunction(js, "function buildFramePickerChoices(artifact)");
            var generatedVideoBranch = ExtractBlock(
                choicesBuilder,
                "if (isVideoArtifactKind(artifact.kind))");

            Assert.Contains("isGeneratedVideoFramePickerRole(file.role)", choicesBuilder);
            Assert.Contains("pickDisplayRole(artifact) || \"image\"", choicesBuilder);
            Assert.DoesNotContain("pickDisplayRole", generatedVideoBranch);
            Assert.DoesNotContain("\"poster\"", generatedVideoBranch);
        }

        [Fact]
        public void AppJs_VideoArtifactKindIncludesGeneratedAndImportedVideos()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("function isVideoArtifactKind(kind)", js);
            var helper = ExtractFunction(js, "function isVideoArtifactKind(kind)");

            Assert.Contains("kind === \"generated_video\" || kind === \"imported_video\"", helper);
        }

        [Fact]
        public void AppJs_GalleryKeepsPosterAsDisplayOnly()
        {
            var js = ReadVisionResource("app.js");

            Assert.Contains("const posterRole = isVideo", js);
            Assert.Contains("f.role === \"poster\"", js);
            Assert.Contains("<img src=\"${posterUrl}\" alt=\"Video poster\">", js);
            Assert.Contains("el.modalVideo.src = src;", js);
            Assert.Contains("modalDisplayRole = pickDisplayRole(modalArtifact);", js);
        }

        private static string ReadVisionResource(string fileName)
        {
            return ReadSourceFile(
                "src",
                "Rook",
                "UI",
                "Vision",
                "Resources",
                fileName);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);

                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }

        private static string ExtractFunction(string source, string signature)
        {
            var signatureIndex = source.IndexOf(signature, StringComparison.Ordinal);
            if (signatureIndex < 0)
                throw new InvalidOperationException("Could not locate function " + signature);

            return ExtractBlock(source, signatureIndex, signature);
        }

        private static string ExtractBlock(string source, string marker)
        {
            var markerIndex = source.IndexOf(marker, StringComparison.Ordinal);
            if (markerIndex < 0)
                throw new InvalidOperationException("Could not locate block " + marker);

            return ExtractBlock(source, markerIndex, marker);
        }

        private static string ExtractBlock(string source, int markerIndex, string marker)
        {
            var bodyStart = source.IndexOf('{', markerIndex);
            if (bodyStart < 0)
                throw new InvalidOperationException("Could not locate block body " + marker);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{')
                    depth++;
                else if (source[i] == '}')
                    depth--;

                if (depth == 0)
                    return source.Substring(markerIndex, i - markerIndex + 1);
            }

            throw new InvalidOperationException("Could not locate block end " + marker);
        }
    }
}
