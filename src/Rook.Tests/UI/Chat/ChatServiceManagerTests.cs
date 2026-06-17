using System;
using System.IO;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class ChatServiceManagerTests
    {
        [Theory]
        [InlineData("net48")]
        [InlineData("net7.0")]
        [InlineData("net8.0")]
        public void ResolveManifestPath_UsesLoadedAssemblyDirectory(string runtime)
        {
            var assemblyLocation = Path.Combine(
                "C:\\Users\\dev\\AppData\\Roaming\\McNeel\\Rhinoceros\\8.0\\Plug-ins\\RookNative",
                runtime,
                "Rook.rhp");

            var path = ChatServiceManager.ResolveManifestPath(assemblyLocation);

            Assert.Equal(
                Path.Combine(
                    "C:\\Users\\dev\\AppData\\Roaming\\McNeel\\Rhinoceros\\8.0\\Plug-ins\\RookNative",
                    runtime,
                    "RookChatService.json"),
                path);
        }

        [Fact]
        public void ResolveManifestPath_DoesNotReturnParentRootManifest()
        {
            var assemblyLocation = Path.Combine("C:\\RookPlugin", "net8.0", "Rook.rhp");

            var path = ChatServiceManager.ResolveManifestPath(assemblyLocation);

            Assert.NotEqual(Path.Combine("C:\\RookPlugin", "RookChatService.json"), path);
            Assert.Equal(Path.Combine("C:\\RookPlugin", "net8.0", "RookChatService.json"), path);
        }

        [Fact]
        public void ValidateManifestRuntime_ReturnsValidForExistingRuntimeAndExpectedOwner()
        {
            var python = CreateTempFile("python.exe");
            var workingDirectory = Directory.CreateDirectory(
                Path.Combine(Path.GetTempPath(), "rook-chat-test-" + Guid.NewGuid().ToString("N"))).FullName;

            try
            {
                var manifest = new ChatServiceManifest
                {
                    PythonPath = python,
                    WorkingDirectory = workingDirectory,
                    Owner = "rhino-panel",
                };

                var result = ChatServiceManager.ValidateManifestRuntime(manifest);

                Assert.True(result.IsValid);
                Assert.Equal("", result.Message);
            }
            finally
            {
                TryDeleteFile(python);
                TryDeleteDirectory(workingDirectory);
            }
        }

        [Fact]
        public void ValidateManifestRuntime_MissingPinnedPythonIsTerminalInvalid()
        {
            var missingPython = Path.Combine(Path.GetTempPath(), "missing-rook-python-" + Guid.NewGuid().ToString("N"), "python.exe");
            var workingDirectory = Directory.CreateDirectory(
                Path.Combine(Path.GetTempPath(), "rook-chat-test-" + Guid.NewGuid().ToString("N"))).FullName;

            try
            {
                var manifest = new ChatServiceManifest
                {
                    PythonPath = missingPython,
                    WorkingDirectory = workingDirectory,
                    Owner = "rhino-panel",
                };

                var result = ChatServiceManager.ValidateManifestRuntime(manifest);

                Assert.False(result.IsValid);
                Assert.Equal($"Python runtime not found: {missingPython}", result.Message);
                Assert.True(result.IsTerminalInvalidManifest);
            }
            finally
            {
                TryDeleteDirectory(workingDirectory);
            }
        }

        [Fact]
        public void ValidateManifestRuntime_MissingWorkingDirectoryIsInvalid()
        {
            var python = CreateTempFile("python.exe");
            var missingDirectory = Path.Combine(Path.GetTempPath(), "missing-rook-working-dir-" + Guid.NewGuid().ToString("N"));

            try
            {
                var manifest = new ChatServiceManifest
                {
                    PythonPath = python,
                    WorkingDirectory = missingDirectory,
                    Owner = "rhino-panel",
                };

                var result = ChatServiceManager.ValidateManifestRuntime(manifest);

                Assert.False(result.IsValid);
                Assert.Equal($"Chat service working directory not found: {missingDirectory}", result.Message);
                Assert.False(result.IsTerminalInvalidManifest);
            }
            finally
            {
                TryDeleteFile(python);
            }
        }

        [Fact]
        public void ValidateManifestRuntime_WrongOwnerIsInvalid()
        {
            var python = CreateTempFile("python.exe");
            var workingDirectory = Directory.CreateDirectory(
                Path.Combine(Path.GetTempPath(), "rook-chat-test-" + Guid.NewGuid().ToString("N"))).FullName;

            try
            {
                var manifest = new ChatServiceManifest
                {
                    PythonPath = python,
                    WorkingDirectory = workingDirectory,
                    Owner = "workbench",
                };

                var result = ChatServiceManager.ValidateManifestRuntime(manifest);

                Assert.False(result.IsValid);
                Assert.Equal("Unsupported chat service owner 'workbench'. Expected 'rhino-panel'.", result.Message);
                Assert.False(result.IsTerminalInvalidManifest);
            }
            finally
            {
                TryDeleteFile(python);
                TryDeleteDirectory(workingDirectory);
            }
        }

        private static string CreateTempFile(string fileName)
        {
            var dir = Directory.CreateDirectory(
                Path.Combine(Path.GetTempPath(), "rook-chat-test-" + Guid.NewGuid().ToString("N"))).FullName;
            var path = Path.Combine(dir, fileName);
            File.WriteAllText(path, "");
            return path;
        }

        private static void TryDeleteFile(string path)
        {
            try
            {
                if (File.Exists(path))
                {
                    var dir = Path.GetDirectoryName(path);
                    File.Delete(path);
                    if (!string.IsNullOrEmpty(dir))
                        TryDeleteDirectory(dir);
                }
            }
            catch
            {
            }
        }

        private static void TryDeleteDirectory(string path)
        {
            try
            {
                if (Directory.Exists(path))
                    Directory.Delete(path, recursive: true);
            }
            catch
            {
            }
        }
    }
}
