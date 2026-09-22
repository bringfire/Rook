using System;
using System.IO;
using System.Text;
using Xunit;

namespace Rook.Tests.Plugin
{
    public class RookPluginLifecycleSourceTests
    {
        [Theory]
        [InlineData(false, true)]
        [InlineData(true, true)]
        public void StartupPanelRegistration_IsEnabledForStandaloneAndRhinoInside(
            bool isRhinoInside,
            bool expected)
        {
            Assert.Equal(
                expected,
                RookPlugin.ShouldRegisterStartupPanels(isRhinoInside));
        }

        [Fact]
        public void StartupPanelRegistration_IsDeferredAndWrappedAsNonFatal()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onLoad = ExtractMethod(source, "protected override LoadReturnCode OnLoad(");
            var registerPanels = ExtractMethod(source, "private void RegisterStartupPanels()");
            var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

            Assert.DoesNotContain("RegisterStartupPanels();", onLoad);
            Assert.Contains("RegisterStartupPanels();", deferredStartup);

            var panelBlock = ExtractTryCatchContaining(
                registerPanels,
                "Panels.RegisterPanel(this, chatPanelType, \"Rook Chat\"");

            Assert.Contains(
                "Panels.RegisterPanel(this, chatPanelType, \"Rook Chat\"",
                panelBlock.TryBody);
            Assert.Contains(
                "Panels.RegisterPanel(this, visionPanelType, \"Rook Vision\"",
                panelBlock.TryBody);
            Assert.Contains(
                "Panels.RegisterPanel(this, kgPanelType, \"Knowledge Graph\"",
                panelBlock.TryBody);
            Assert.Contains(
                "TraceStartup($\"Panel registration failed (non-fatal):",
                panelBlock.CatchBody);
            Assert.DoesNotContain("throw", panelBlock.CatchBody);
        }

        [Fact]
        public void OnLoad_IsMinimalAndDoesNotRunCompanionStartupSideEffects()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onLoad = ExtractMethod(source, "protected override LoadReturnCode OnLoad(");

            Assert.Contains("TraceStartup(\"OnLoad minimal\");", onLoad);
            Assert.Contains("AttachStartupGateHooks();", onLoad);
            Assert.Contains("return LoadReturnCode.Success;", onLoad);

            Assert.DoesNotContain("RegisterStartupPanels();", onLoad);
            Assert.DoesNotContain("RhinoApp.InvokeOnUiThread", onLoad);
            Assert.DoesNotContain("BeginStartupRetries();", onLoad);
            Assert.DoesNotContain("TryInitializeRuntime();", onLoad);
            Assert.DoesNotContain("NativeGhBridgeRegistrar.TryRegister", onLoad);
            Assert.DoesNotContain("EnsureToolbarLoaded();", onLoad);
            Assert.DoesNotContain("RhinoApp.WriteLine", onLoad);
        }

        [Fact]
        public void OnLoad_ConfiguresVertexTokenSourceBeforeDeferredImageAccess()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onLoad = ExtractMethod(source, "protected override LoadReturnCode OnLoad(");

            var configureIndex = onLoad.IndexOf(
                "RookSubsystemRoot.Instance.ConfigureVertexAccessTokenSource(",
                StringComparison.Ordinal);
            var hooksIndex = onLoad.IndexOf("AttachStartupGateHooks();", StringComparison.Ordinal);

            Assert.True(configureIndex >= 0, "OnLoad must configure the concrete Vertex token source.");
            Assert.Contains("ChatServiceVertexAccessTokenSource.Instance", onLoad);
            Assert.True(hooksIndex >= 0, "OnLoad must still attach deferred startup hooks.");
            Assert.True(
                configureIndex < hooksIndex,
                "Vertex token composition must precede all deferred image access.");
        }

        [Fact]
        public void LegacyRuiToolbar_HasNoActiveManagedLoader()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            Assert.DoesNotContain("_toolbarLoaded", source);
            Assert.DoesNotContain("EnsureToolbarLoaded", source);
            Assert.DoesNotContain("LoadToolbar", source);
            Assert.DoesNotContain("Rook.rui", source);
            Assert.DoesNotContain("ToolbarFiles.Open", source);
        }

        [Fact]
        public void RuntimeStatus_IsPublishedOnLoadAndStartupTransitions()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onLoad = ExtractMethod(source, "protected override LoadReturnCode OnLoad(");
            var runFromIdle = ExtractMethod(source, "private void RunDeferredStartupFromIdle()");
            var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");
            var writeStatus = ExtractMethod(source, "private void WriteCompanionRuntimeStatus()");

            Assert.Contains("_onLoadUtc = DateTimeOffset.UtcNow;", onLoad);
            Assert.Contains("WriteCompanionRuntimeStatus();", onLoad);
            Assert.Contains("WriteCompanionRuntimeStatus();", runFromIdle);
            Assert.Contains("WriteCompanionRuntimeStatus();", deferredStartup);
            Assert.Contains("CompanionRuntimeStatus.CreateSnapshot", writeStatus);
            Assert.Contains("CompanionRuntimeStatus.Write", writeStatus);
            Assert.Contains("bridgeRegistered: _bridgeRegistered", writeStatus);
            Assert.Contains("startupComplete: _startupComplete", writeStatus);
        }

        [Fact]
        public void ShowRookChatCommand_VerifiesPanelVisibilityAfterOpen()
        {
            var source = ReadSourceFile("src", "Rook", "Commands", "ShowRookChatCommand.cs");

            Assert.Contains("Panels.OpenPanel(panelId);", source);
            Assert.Contains("IsRookChatPanelVisible()", source);
            Assert.Contains("could not be shown", source);
            Assert.Contains("return Result.Failure;", source);
        }

        [Fact]
        public void ChatServiceManifestFallback_KnowsReleaseInstallLayout()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatServiceManager.cs");
            var autoGenerate = ExtractMethod(source, "private static ChatServiceManifest? TryAutoGenerateManifest(");
            var releaseRoot = ExtractMethod(source, "private static string? GetReleaseInstallRoot()");
            var managedPython = ExtractMethod(source, "private static string? DiscoverManagedVenvPython()");

            Assert.Contains("GetReleaseInstallRoot();", autoGenerate);
            Assert.Contains("Path.Combine(releaseInstallRoot, \"mcp_server\")", autoGenerate);
            Assert.Contains("candidates.Add(releaseInstallRoot);", autoGenerate);
            Assert.Contains("pythonPath = DiscoverManagedVenvPython();", autoGenerate);
            Assert.Contains("AllowUserPythonDiscovery()", autoGenerate);
            Assert.Contains("pythonPath = DiscoverPython();", autoGenerate);

            Assert.Contains("\"Rook\", \"app\"", releaseRoot);
            Assert.Contains("\"Rook\", \"venv\", \"Scripts\", \"python.exe\"", managedPython);
        }

        [Fact]
        public void StartupVideoReconcileFailure_IsCaughtAndLoggedAsNonFatal()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onLoad = ExtractMethod(source, "protected override LoadReturnCode OnLoad(");
            var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

            Assert.DoesNotContain("BeginStartupRetries();", onLoad);
            Assert.DoesNotContain("RhinoApp.InvokeOnUiThread(new Action(TryInitializeRuntime));", onLoad);
            Assert.Contains("return LoadReturnCode.Success;", onLoad);

            var reconcileBlock = ExtractTryCatchContaining(
                deferredStartup,
                "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();");

            Assert.Contains(
                "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();",
                reconcileBlock.TryBody);
            Assert.Contains(
                "TraceStartup(\"Video subsystem reconciled",
                reconcileBlock.TryBody);
            Assert.Contains(
                "TraceStartup($\"Video reconcile failed (non-fatal):",
                reconcileBlock.CatchBody);
            Assert.Contains(
                "continuing without reconcile",
                reconcileBlock.CatchBody);
            Assert.DoesNotContain("throw", reconcileBlock.CatchBody);
        }

        [Fact]
        public void ShutdownExternalTeardownSteps_HaveIndependentTryCatchWrappers()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onShutdown = ExtractMethod(source, "protected override void OnShutdown()");
            var steps = new[]
            {
                new TeardownStep(
                    "NativeGhBridgeRegistrar.ClearRegistration();",
                    "Native GH bridge clear failed"),
                new TeardownStep(
                    "ChatServiceManager.Instance.Shutdown();",
                    "Chat service shutdown failed"),
                new TeardownStep(
                    "RookSubsystemRoot.Instance.DisposeCreatedSubsystems();",
                    "Video subsystem dispose failed"),
            };

            foreach (var step in steps)
            {
                var block = ExtractTryCatchContaining(onShutdown, step.Call);

                Assert.Contains(step.Call, block.TryBody);
                Assert.Contains(step.FailureLog, block.CatchBody);
                Assert.DoesNotContain("throw", block.CatchBody);

                foreach (var other in steps)
                {
                    if (ReferenceEquals(step, other))
                        continue;

                    Assert.DoesNotContain(other.Call, block.TryBody);
                }
            }
        }

        [Fact]
        public void StartupVideoSidecarBackfill_IsScheduledAsSeparateNonFatalAsyncStep()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

            var reconcileBlock = ExtractTryCatchContaining(
                deferredStartup,
                "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();");
            Assert.DoesNotContain("BackfillVideoSidecarsOnce", reconcileBlock.TryBody);

            var backfillBlock = ExtractTryCatchContaining(
                deferredStartup,
                "RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(");

            Assert.Contains(
                "RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(",
                backfillBlock.TryBody);
            Assert.Contains(
                "VideoSidecarBackfillStartupOptions",
                backfillBlock.TryBody);
            Assert.Contains(
                "TraceStartup($\"Video sidecar backfill completed:",
                backfillBlock.TryBody);
            Assert.Contains(
                "TraceStartup($\"Video sidecar backfill failed (non-fatal):",
                backfillBlock.TryBody);
            Assert.Contains(
                "TraceStartup($\"Video sidecar backfill scheduling failed (non-fatal):",
                backfillBlock.CatchBody);
            Assert.DoesNotContain("throw", backfillBlock.CatchBody);
        }

        [Fact]
        public void StartupGateHooks_UseIdleAndDocumentOpenLifecycle()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var attach = ExtractMethod(source, "private void AttachStartupGateHooks()");
            var detach = ExtractMethod(source, "private void DetachStartupGateHooks()");

            Assert.Contains("RhinoApp.Idle += OnStartupGateIdle;", attach);
            Assert.Contains("RhinoDoc.BeginOpenDocument += OnBeginOpenDocument;", attach);
            Assert.Contains("RhinoDoc.EndOpenDocument += OnEndOpenDocument;", attach);
            Assert.Contains(
                "RhinoDoc.EndOpenDocumentInitialViewUpdate += OnEndOpenDocumentInitialViewUpdate;",
                attach);

            Assert.Contains("RhinoApp.Idle -= OnStartupGateIdle;", detach);
            Assert.Contains("RhinoDoc.BeginOpenDocument -= OnBeginOpenDocument;", detach);
            Assert.Contains("RhinoDoc.EndOpenDocument -= OnEndOpenDocument;", detach);
            Assert.Contains(
                "RhinoDoc.EndOpenDocumentInitialViewUpdate -= OnEndOpenDocumentInitialViewUpdate;",
                detach);
            Assert.Contains("TraceStartup(\"StartupGate hooks detached\");", detach);
        }

        [Fact]
        public void StartupGateIdle_UsesDocumentOpenLifecycleBlockingAdapter()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var idle = ExtractMethod(source, "private void OnStartupGateIdle(");
            var blocker = ExtractMethod(source, "private bool IsDocumentOpenLifecycleBlocking()");
            var docBlocker = ExtractMethod(source, "private static bool IsActiveDocumentOpenLifecycleBlocking()");

            Assert.Contains("DocumentOpening: IsDocumentOpenLifecycleBlocking()", idle);
            Assert.DoesNotContain("DocumentOpening: _documentOpening", idle);

            Assert.Contains("if (_documentOpening)", blocker);
            Assert.Contains("IsActiveDocumentOpenLifecycleBlocking()", blocker);
            Assert.Contains("!_documentOpenInitialViewReady && IsRhinoCommandActive()", blocker);

            Assert.Contains("RhinoDoc.ActiveDoc", docBlocker);
            Assert.Contains("if (doc == null)", docBlocker);
            Assert.Contains("doc.IsOpening", docBlocker);
            Assert.Contains("doc.IsInitializing", docBlocker);
            Assert.Contains("!doc.IsAvailable", docBlocker);
            Assert.Contains("catch", docBlocker);
            Assert.Contains("return true;", docBlocker);
        }

        [Fact]
        public void DeferredStartupFailure_IsCaughtAndAllowsIdleRetry()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var runFromIdle = ExtractMethod(source, "private void RunDeferredStartupFromIdle()");

            Assert.Contains("catch (Exception ex)", runFromIdle);
            Assert.Contains("Deferred startup failed (will retry):", runFromIdle);
            Assert.Contains("if (!_shutdownStarted)", runFromIdle);
            Assert.Contains("_startupGate.MarkStartupAvailableForRetry();", runFromIdle);
        }

        [Fact]
        public void BridgeUnavailableAfterQuiescence_RetriesThroughIdleOnly()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var idle = ExtractMethod(source, "private void OnStartupGateIdle(");
            var wait = ExtractMethod(source, "private bool IsWaitingForBridgeRetry()");
            var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

            Assert.Contains("if (IsWaitingForBridgeRetry())", idle);
            Assert.Contains("return;", idle);
            Assert.Contains("StartupGate bridge retry waiting for throttle interval", wait);
            Assert.Contains("_startupGate.MarkStartupAvailableForRetry();", wait);
            Assert.Contains("NativeGhBridgeRegistrar.TryRegister();", deferredStartup);
            Assert.DoesNotContain("_startupGate.MarkStartupAvailableForRetry();", deferredStartup);
            Assert.Contains("BridgeRetryLimit", source);
            Assert.Contains("BridgeRetryInterval", source);
            Assert.Contains("_nextBridgeRetryUtc = nowUtc + BridgeRetryInterval;", deferredStartup);
            Assert.Contains("_nextBridgeRetryUtc", deferredStartup);
            Assert.DoesNotContain("RhinoApp.InvokeOnUiThread", deferredStartup);
            Assert.DoesNotContain("new Timer", deferredStartup);
        }

        [Fact]
        public void StartupRetryTimer_IsRemovedFromManagedCompanionStartup()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");

            Assert.DoesNotContain("new Timer", source);
            Assert.DoesNotContain("_startupRetryTimer", source);
            Assert.DoesNotContain("StartupRetryIntervalMs", source);
            Assert.DoesNotContain("BeginStartupRetries", source);
            Assert.DoesNotContain("ScheduleNextStartupRetry", source);
            Assert.DoesNotContain("StopStartupRetries", source);
        }

        [Fact]
        public void BridgeRetryExhausted_DoesNotSuppressDeferredUiStartup()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

            var localStartupIndex = deferredStartup.IndexOf(
                "_deferredLocalStartupComplete = true;",
                StringComparison.Ordinal);
            var bridgeIndex = deferredStartup.IndexOf(
                "NativeGhBridgeRegistrar.TryRegister();",
                StringComparison.Ordinal);
            var exhaustionIndex = deferredStartup.IndexOf(
                "Startup bridge retries exhausted",
                StringComparison.Ordinal);

            Assert.True(localStartupIndex >= 0, "Local startup completion must be recorded.");
            Assert.True(bridgeIndex >= 0, "Bridge registration must be attempted after local startup.");
            Assert.True(exhaustionIndex >= 0, "Bridge retry exhaustion must be explicit.");
            Assert.True(
                localStartupIndex < bridgeIndex,
                "Local UI/runtime startup must complete before bridge registration.");
            Assert.True(
                bridgeIndex < exhaustionIndex,
                "Bridge exhaustion must not run before local UI/runtime startup.");
        }

        [Fact]
        public void LocalReconcileAndBackfill_RunBeforeBridgeRegistration()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var deferredStartup = ExtractMethod(source, "private bool RunDeferredCompanionStartup()");

            var videoIndex = deferredStartup.IndexOf(
                "RookSubsystemRoot.Instance.ReconcileVideoJobsOnce();",
                StringComparison.Ordinal);
            var imageIndex = deferredStartup.IndexOf(
                "RookSubsystemRoot.Instance.ReconcileImageJobsOnce();",
                StringComparison.Ordinal);
            var backfillIndex = deferredStartup.IndexOf(
                "RookSubsystemRoot.Instance.BackfillVideoSidecarsOnce(",
                StringComparison.Ordinal);
            var bridgeIndex = deferredStartup.IndexOf(
                "NativeGhBridgeRegistrar.TryRegister();",
                StringComparison.Ordinal);

            Assert.True(videoIndex >= 0, "Video reconcile must still run after quiescence.");
            Assert.True(imageIndex >= 0, "Image reconcile must still run after quiescence.");
            Assert.True(backfillIndex >= 0, "Video sidecar backfill must still be scheduled after quiescence.");
            Assert.True(bridgeIndex >= 0, "Bridge registration must still be attempted.");
            Assert.True(videoIndex < bridgeIndex, "Video reconcile must not wait for bridge registration.");
            Assert.True(imageIndex < bridgeIndex, "Image reconcile must not wait for bridge registration.");
            Assert.True(backfillIndex < bridgeIndex, "Backfill must not wait for bridge registration.");
        }

        [Fact]
        public void Constructor_DoesNotSubscribeStartupIdleHandlers()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var constructor = ExtractMethod(source, "public RookPlugin()");

            Assert.DoesNotContain("RhinoApp.Idle +=", constructor);
            Assert.DoesNotContain("OnRhinoIdle", source);
            Assert.DoesNotContain("EnsureNativeGhBridgeRegistered", source);
            Assert.DoesNotContain("BeginStartupRetries", source);
            Assert.DoesNotContain("ScheduleNextStartupRetry", source);
            Assert.DoesNotContain("new Timer", source);
        }

        [Fact]
        public void ShutdownBaseCall_RemainsAfterAndOutsideTeardownTryCatchWrappers()
        {
            var source = ReadSourceFile("src", "Rook", "RookPlugin.cs");
            var onShutdown = ExtractMethod(source, "protected override void OnShutdown()");

            var baseCallIndex = onShutdown.IndexOf("base.OnShutdown();", StringComparison.Ordinal);
            Assert.True(baseCallIndex >= 0, "base.OnShutdown() must remain in OnShutdown.");

            Assert.True(
                baseCallIndex > onShutdown.IndexOf(
                    "NativeGhBridgeRegistrar.ClearRegistration();",
                    StringComparison.Ordinal),
                "base.OnShutdown() must remain after bridge registration cleanup.");
            Assert.True(
                baseCallIndex > onShutdown.IndexOf(
                    "ChatServiceManager.Instance.Shutdown();",
                    StringComparison.Ordinal),
                "base.OnShutdown() must remain after chat service shutdown.");
            Assert.True(
                baseCallIndex > onShutdown.IndexOf(
                    "RookSubsystemRoot.Instance.DisposeCreatedSubsystems();",
                    StringComparison.Ordinal),
                "base.OnShutdown() must remain after video subsystem disposal.");

            Assert.Throws<InvalidOperationException>(
                () => ExtractTryCatchContaining(onShutdown, "base.OnShutdown();"));
        }

        private static TryCatchBlock ExtractTryCatchContaining(
            string source,
            string containedText)
        {
            var searchStart = 0;
            while (searchStart < source.Length)
            {
                var tryIndex = source.IndexOf("try", searchStart, StringComparison.Ordinal);
                if (tryIndex < 0)
                    break;

                if (!IsStandaloneWord(source, tryIndex, "try".Length))
                {
                    searchStart = tryIndex + "try".Length;
                    continue;
                }

                var bodyStart = source.IndexOf('{', tryIndex);
                if (bodyStart < 0)
                    break;

                var betweenKeywordAndBody = source.Substring(
                    tryIndex + "try".Length,
                    bodyStart - tryIndex - "try".Length);
                if (!string.IsNullOrWhiteSpace(betweenKeywordAndBody))
                {
                    searchStart = tryIndex + "try".Length;
                    continue;
                }

                var bodyEnd = FindMatchingBrace(source, bodyStart);
                var tryBody = source.Substring(bodyStart + 1, bodyEnd - bodyStart - 1);
                if (!tryBody.Contains(containedText))
                {
                    searchStart = bodyEnd + 1;
                    continue;
                }

                var catchIndex = NextNonWhitespaceIndex(source, bodyEnd + 1);
                if (!StartsWithAt(source, catchIndex, "catch"))
                {
                    searchStart = tryIndex + "try".Length;
                    continue;
                }

                var catchBodyStart = source.IndexOf('{', catchIndex);
                if (catchBodyStart < 0)
                    throw new InvalidOperationException(
                        "catch body not found for text: " + containedText);

                var catchBodyEnd = FindMatchingBrace(source, catchBodyStart);
                var catchBody = source.Substring(
                    catchBodyStart + 1,
                    catchBodyEnd - catchBodyStart - 1);
                return new TryCatchBlock(tryBody, catchBody);
            }

            throw new InvalidOperationException(
                "try/catch block not found for text: " + containedText);
        }

        private static string ExtractMethod(string source, string signatureStartText)
        {
            var signatureStart = source.IndexOf(
                signatureStartText,
                StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException(
                    "Method not found: " + signatureStartText);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException(
                    "Method body not found: " + signatureStartText);

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

            throw new InvalidOperationException(
                "Brace did not close at index " + openBraceIndex);
        }

        private static int NextNonWhitespaceIndex(string source, int start)
        {
            for (var i = start; i < source.Length; i++)
            {
                if (!char.IsWhiteSpace(source[i]))
                    return i;
            }

            return source.Length;
        }

        private static bool StartsWithAt(string source, int index, string value)
        {
            return index >= 0
                && index + value.Length <= source.Length
                && string.Compare(
                    source,
                    index,
                    value,
                    0,
                    value.Length,
                    StringComparison.Ordinal) == 0;
        }

        private static bool IsStandaloneWord(string source, int index, int length)
        {
            var before = index == 0 ? '\0' : source[index - 1];
            var afterIndex = index + length;
            var after = afterIndex >= source.Length ? '\0' : source[afterIndex];
            return !IsIdentifierChar(before) && !IsIdentifierChar(after);
        }

        private static bool IsIdentifierChar(char value)
        {
            return char.IsLetterOrDigit(value) || value == '_';
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return RemoveComments(File.ReadAllText(candidate));

                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }

        private static string RemoveComments(string source)
        {
            var builder = new StringBuilder(source.Length);
            var inLineComment = false;
            var inBlockComment = false;
            var inString = false;
            var inVerbatimString = false;
            var inChar = false;

            for (var i = 0; i < source.Length; i++)
            {
                var current = source[i];
                var next = i + 1 < source.Length ? source[i + 1] : '\0';

                if (inLineComment)
                {
                    if (current == '\r' || current == '\n')
                    {
                        inLineComment = false;
                        builder.Append(current);
                    }
                    else
                    {
                        builder.Append(' ');
                    }

                    continue;
                }

                if (inBlockComment)
                {
                    if (current == '*' && next == '/')
                    {
                        builder.Append("  ");
                        i++;
                        inBlockComment = false;
                    }
                    else
                    {
                        builder.Append(current == '\r' || current == '\n' ? current : ' ');
                    }

                    continue;
                }

                if (inString)
                {
                    builder.Append(current);

                    if (inVerbatimString)
                    {
                        if (current == '"' && next == '"')
                        {
                            builder.Append(next);
                            i++;
                        }
                        else if (current == '"')
                        {
                            inString = false;
                            inVerbatimString = false;
                        }
                    }
                    else if (current == '\\' && next != '\0')
                    {
                        builder.Append(next);
                        i++;
                    }
                    else if (current == '"')
                    {
                        inString = false;
                    }

                    continue;
                }

                if (inChar)
                {
                    builder.Append(current);

                    if (current == '\\' && next != '\0')
                    {
                        builder.Append(next);
                        i++;
                    }
                    else if (current == '\'')
                    {
                        inChar = false;
                    }

                    continue;
                }

                if (current == '/' && next == '/')
                {
                    builder.Append("  ");
                    i++;
                    inLineComment = true;
                    continue;
                }

                if (current == '/' && next == '*')
                {
                    builder.Append("  ");
                    i++;
                    inBlockComment = true;
                    continue;
                }

                if (current == '"')
                {
                    inString = true;
                    inVerbatimString = IsVerbatimStringStart(source, i);
                    builder.Append(current);
                    continue;
                }

                if (current == '\'')
                {
                    inChar = true;
                    builder.Append(current);
                    continue;
                }

                builder.Append(current);
            }

            return builder.ToString();
        }

        private static bool IsVerbatimStringStart(string source, int quoteIndex)
        {
            return quoteIndex > 0 && source[quoteIndex - 1] == '@'
                || quoteIndex > 1
                && source[quoteIndex - 2] == '@'
                && source[quoteIndex - 1] == '$';
        }

        private sealed class TeardownStep
        {
            public TeardownStep(string call, string failureLog)
            {
                Call = call;
                FailureLog = failureLog;
            }

            public string Call { get; }

            public string FailureLog { get; }
        }

        private sealed class TryCatchBlock
        {
            public TryCatchBlock(string tryBody, string catchBody)
            {
                TryBody = tryBody;
                CatchBody = catchBody;
            }

            public string TryBody { get; }

            public string CatchBody { get; }
        }
    }
}
