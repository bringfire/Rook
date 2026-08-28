using System;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class ChatServiceManagerTests
    {
        [Fact]
        public async Task Manager_owned_Prime_close_carries_nonce_and_has_a_deadline()
        {
            var handler = new CapturingHandler();
            using var client = new HttpClient(handler);

            await ChatServiceManager.SendOwnedPrimeCloseAsync(
                client,
                new Uri("http://localhost:8765"),
                "conv_0123456789abcdef0123456789abcdef",
                "owned-nonce",
                TimeSpan.FromSeconds(1));

            Assert.Equal("/agent/chat/stop", handler.Path);
            Assert.Equal("owned-nonce", handler.Nonce);
            Assert.Contains("conv_0123456789abcdef0123456789abcdef", handler.Body);
        }

        [Fact]
        public async Task Manager_owned_Prime_close_refuses_an_unbounded_wait()
        {
            var handler = new CapturingHandler { NeverComplete = true };
            using var client = new HttpClient(handler);

            await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
                ChatServiceManager.SendOwnedPrimeCloseAsync(
                    client,
                    new Uri("http://localhost:8765"),
                    "conv_0123456789abcdef0123456789abcdef",
                    "owned-nonce",
                    TimeSpan.FromMilliseconds(20)));
        }
        [Fact]
        public void BuildServiceArguments_includes_process_generation_fingerprint()
        {
            Assert.Equal(
                "-m rook.agent.chat.service_main --port 0 --owner rhino-panel " +
                "--rhino-process-id 1234 --rhino-process-start-utc-ticks 638918000000000000",
                ChatServiceManager.BuildServiceArguments(
                    1234,
                    "638918000000000000"));
        }

        [Theory]
        [InlineData("legacy", true)]
        [InlineData("", true)]
        [InlineData("prime", false)]
        public void Prime_launch_does_not_copy_legacy_credentials(
            string backend,
            bool expected)
        {
            Assert.Equal(
                expected,
                ChatServiceManager.ShouldCopyLegacyCredentials(backend));
        }

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

        [Fact]
        public void LoadManifest_DoesNotRegenerateWhenPinnedPythonIsMissing()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatServiceManager.cs");
            var loadManifest = ExtractMethod(source, "private ChatServiceManifest? LoadManifest()");

            Assert.Contains("ValidateManifestRuntime(manifest)", loadManifest);
            Assert.Contains("runtimeValidation.IsTerminalInvalidManifest", loadManifest);
            var terminalInvalidIndex = loadManifest.IndexOf(
                "runtimeValidation.IsTerminalInvalidManifest",
                StringComparison.Ordinal);
            var terminalReturnIndex = loadManifest.IndexOf(
                "return manifest;",
                terminalInvalidIndex,
                StringComparison.Ordinal);
            var staleCheckIndex = loadManifest.IndexOf(
                "IsManifestCurrent(manifest",
                StringComparison.Ordinal);
            var autoGenerateIndex = loadManifest.IndexOf(
                "TryAutoGenerateManifest(manifestPath)",
                StringComparison.Ordinal);

            Assert.True(terminalInvalidIndex >= 0);
            Assert.True(terminalReturnIndex > terminalInvalidIndex);
            Assert.True(terminalReturnIndex < staleCheckIndex);
            Assert.True(terminalReturnIndex < autoGenerateIndex);
        }

        [Theory]
        [InlineData(true, false, false, true, "ReuseHealthyService")]
        [InlineData(true, false, true, true, "ReuseHealthyService")]
        [InlineData(true, false, false, false, "RestartBecauseNonceMissing")]
        [InlineData(true, false, true, false, "RestartBecauseNonceMissing")]
        public void ShouldStartChatService_HealthyServiceDecision(
            bool existingServiceAvailable,
            bool trackedProcessExists,
            bool trackedProcessHasExited,
            bool sessionNoncePresent,
            string expected)
        {
            var decision = ChatServiceManager.ShouldStartChatService(
                trackedProcessExists,
                trackedProcessHasExited,
                existingServiceAvailable,
                sessionNoncePresent);

            Assert.Equal(expected, decision.ToString());
        }

        [Theory]
        [InlineData(true, false, false, false, "WaitForTrackedProcess")]
        [InlineData(true, false, false, true, "WaitForTrackedProcess")]
        [InlineData(true, true, false, true, "StartNewProcess")]
        [InlineData(false, false, false, true, "StartNewProcess")]
        public void ShouldStartChatService_TrackedProcessDecision(
            bool trackedProcessExists,
            bool trackedProcessHasExited,
            bool existingServiceAvailable,
            bool sessionNoncePresent,
            string expected)
        {
            var decision = ChatServiceManager.ShouldStartChatService(
                trackedProcessExists,
                trackedProcessHasExited,
                existingServiceAvailable,
                sessionNoncePresent);

            Assert.Equal(expected, decision.ToString());
        }

        [Fact]
        public void EnsureStartedAndStartProcessKeepLifecycleLockAndPinnedInterpreter()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatServiceManager.cs");
            var ensureStarted = ExtractMethod(source, "public async Task<ChatServiceHealth> EnsureStartedAsync(");
            var startProcess = ExtractMethod(source, "private void StartProcess(");

            Assert.Contains("await _gate.WaitAsync(ct);", ensureStarted);
            Assert.Contains("ShouldStartChatService(", ensureStarted);
            Assert.Contains("ChatServiceStartDecision.RestartBecauseNonceMissing", ensureStarted);
            Assert.Contains("StartProcess(manifest);", ensureStarted);
            Assert.Contains("FileName = manifest.PythonPath", startProcess);
            Assert.Contains("ShouldStartChatService(", startProcess);
            Assert.DoesNotContain("DiscoverPython()", startProcess);
            Assert.DoesNotContain("DiscoverManagedVenvPython()", startProcess);
        }

        private static string CreateTempFile(string fileName)
        {
            var dir = Directory.CreateDirectory(
                Path.Combine(Path.GetTempPath(), "rook-chat-test-" + Guid.NewGuid().ToString("N"))).FullName;
            var path = Path.Combine(dir, fileName);
            File.WriteAllText(path, "");
            return path;
        }

        private sealed class CapturingHandler : HttpMessageHandler
        {
            public bool NeverComplete { get; set; }
            public string? Path { get; private set; }
            public string? Nonce { get; private set; }
            public string Body { get; private set; } = "";

            protected override async Task<HttpResponseMessage> SendAsync(
                HttpRequestMessage request,
                CancellationToken cancellationToken)
            {
                Path = request.RequestUri?.AbsolutePath;
                Nonce = request.Headers.TryGetValues(
                    "X-Rook-Session", out var values)
                    ? System.Linq.Enumerable.FirstOrDefault(values)
                    : null;
                Body = request.Content == null
                    ? ""
                    : await request.Content.ReadAsStringAsync();
                if (NeverComplete)
                    await Task.Delay(Timeout.Infinite, cancellationToken);
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                };
            }
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

            throw new FileNotFoundException("Could not locate source file " + string.Join("/", pathParts));
        }

        private static string ExtractMethod(string source, string signatureStartText)
        {
            var signatureStart = source.IndexOf(signatureStartText, StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Method not found: " + signatureStartText);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Method body not found: " + signatureStartText);

            var bodyEnd = FindMatchingBrace(source, bodyStart);
            return source.Substring(signatureStart, bodyEnd - signatureStart + 1);
        }

        private static int FindMatchingBrace(string source, int openBraceIndex)
        {
            var depth = 0;
            for (var i = openBraceIndex; i < source.Length; i++)
            {
                if (source[i] == '{')
                    depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return i;
                }
            }

            throw new InvalidOperationException("Brace did not close at index " + openBraceIndex);
        }
    }
}
