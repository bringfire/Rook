using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Threading
{
    public class MainThreadDispatcherSourceTests
    {
        [Fact]
        public void Dispatch_DefaultsToNormalPolicy()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");

            Assert.Contains("DispatchPolicy policy = DispatchPolicy::Normal", source);
            Assert.Contains("enum class DispatchPolicy", source);
            Assert.Contains("CommandControl", source);
        }

        [Fact]
        public void QueuedTask_CarriesPolicyTaskAndCancel()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
            var queuedTask = ExtractStruct(source, "QueuedTask");

            Assert.Contains("DispatchPolicy policy", queuedTask);
            Assert.Contains("std::function<void()> task", queuedTask);
            Assert.Contains("std::function<void()> cancel", queuedTask);
        }

        [Fact]
        public void Dispatch_CancelsNormalTasksWithDeterministicBusyException()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
            var dispatch = ExtractFunction(source, "CMainThreadDispatcher::Dispatch");

            Assert.Contains("std::make_shared<std::promise<ReturnType>>", dispatch);
            Assert.Contains("promise->set_exception(std::make_exception_ptr(", dispatch);
            Assert.Contains("std::runtime_error(\"RookNative dispatcher is busy: Rhino command is active\")", dispatch);
        }

        [Fact]
        public void DrainQueue_BlocksAllDispatchDuringSave()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
            var drainQueue = ExtractFunction(source, "CMainThreadDispatcher::DrainQueue");

            Assert.Contains("if (IsAllDispatchBlocked())", drainQueue);
            Assert.True(
                drainQueue.IndexOf("if (IsAllDispatchBlocked())", StringComparison.Ordinal)
                < drainQueue.IndexOf("IsNormalDispatchBlocked()", StringComparison.Ordinal),
                "Save guard must block before command-control filtering.");
        }

        [Fact]
        public void EndSaveGuard_PostsWhenSaveDepthReleasesEvenIfCommandActive()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
            var endSaveGuard = ExtractFunction(source, "CMainThreadDispatcher::EndSaveGuard");

            Assert.Contains("shouldPostDispatch = (current == 1);", endSaveGuard);
            Assert.Contains("PostMessage(m_subclassedHwnd, WM_ROOK_DISPATCH", endSaveGuard);
            Assert.DoesNotContain("IsNormalDispatchBlocked()", endSaveGuard);
            Assert.DoesNotContain("IsCommandActive()", endSaveGuard);
        }

        [Fact]
        public void DrainQueue_CommandActiveRunsCommandControlAndCancelsNormal()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
            var drainQueue = ExtractFunction(source, "CMainThreadDispatcher::DrainQueue");

            Assert.Contains("const bool normalDispatchBlocked = IsNormalDispatchBlocked();", drainQueue);
            Assert.Contains("std::queue<QueuedTask> blockedNormal", drainQueue);
            Assert.Contains("queued.policy == DispatchPolicy::CommandControl", drainQueue);
            Assert.Contains("commandControl.push(std::move(queued))", drainQueue);
            Assert.Contains("blockedNormal.push(std::move(queued))", drainQueue);
            Assert.Contains("CancelQueuedTasks(blockedNormal);", drainQueue);
        }

        [Fact]
        public void DrainQueue_RechecksNormalTasksBeforeExecutionAndCancelsWhenCommandStarts()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
            var drainQueue = ExtractFunction(source, "CMainThreadDispatcher::DrainQueue");

            Assert.Contains(
                "queued.policy == DispatchPolicy::Normal && IsNormalDispatchBlocked()",
                drainQueue);
            Assert.Contains("std::queue<QueuedTask> blockedNormal", drainQueue);
            Assert.Contains("std::queue<QueuedTask> commandControl", drainQueue);
            Assert.Contains("blockedNormal.push(std::move(queued));", drainQueue);
            Assert.Contains("commandControl.push(std::move(queued));", drainQueue);
            Assert.Contains("CancelQueuedTasks(blockedNormal);", drainQueue);
            Assert.Contains("std::swap(local, commandControl);", drainQueue);
            Assert.DoesNotContain("deferredNormal", drainQueue);
        }

        [Fact]
        public void CommandInteractive_OnlyPromptSendCancelAndEscapeUseCommandControl()
        {
            var commandSource = ReadSourceFile("src", "RookNative", "Handlers", "CommandInteractiveHandler.cpp");
            var promptSource = ReadSourceFile("src", "RookNative", "Interactive", "PromptManager.cpp");

            var prompt = ExtractFunction(commandSource, "TryReadPromptOnMain");
            var start = ExtractFunction(commandSource, "HandleCommandStart");
            var input = ExtractFunction(commandSource, "HandleCommandInput");
            var cancel = ExtractFunction(commandSource, "HandleCommandCancel");
            var escape = ExtractFunction(promptSource, "PostEscapeToRhino");

            Assert.Contains("DispatchPolicy::CommandControl", prompt);
            Assert.DoesNotContain("DispatchPolicy::CommandControl", start);
            Assert.Contains("DispatchPolicy::CommandControl", input);
            Assert.Contains("DispatchPolicy::CommandControl", cancel);
            Assert.Contains("DispatchPolicy::CommandControl", escape);

            Assert.DoesNotContain("CRhinoObjectIterator", input);
            Assert.DoesNotContain("objects_before", input);
        }

        [Fact]
        public void CompanionLoad_UsesNormalDispatchAndNeverCommandControl()
        {
            var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");
            var attemptLoad = ExtractFunction(source, "AttemptCompanionLoadOnMainThread");

            Assert.Contains("CMainThreadDispatcher::Instance().Dispatch([", attemptLoad);
            Assert.DoesNotContain("DispatchPolicy::CommandControl", attemptLoad);
            Assert.DoesNotContain("CommandControl", attemptLoad);
            Assert.DoesNotContain("DispatchPolicy::CommandControl", companionLoad);
            Assert.DoesNotContain("CommandControl", companionLoad);
        }

        [Fact]
        public void CompanionLoad_ClassifiesCommandActiveBusyAsDeferral()
        {
            var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");

            Assert.Contains("enum class CompanionLoadAttemptResult", source);
            Assert.Contains("NotSafeYet", source);
            Assert.Contains("ClassifyCompanionLoadException", source);
            Assert.Contains("RookNative dispatcher is busy: Rhino command is active", source);
            Assert.Contains("case CompanionLoadAttemptResult::NotSafeYet:", companionLoad);
            Assert.Contains("WriteCompanionLoadDiagnostic", companionLoad);
            Assert.Contains("continue;", companionLoad);
        }

        [Fact]
        public void CompanionLoad_DispatchedLambdaReturnsResultWithoutStackReferenceCapture()
        {
            var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var attemptLoad = ExtractFunction(source, "AttemptCompanionLoadOnMainThread");

            Assert.Contains("CMainThreadDispatcher::Instance().Dispatch([]() -> CompanionLoadAttemptResult", attemptLoad);
            Assert.Contains("return CompanionLoadAttemptResult::Loaded;", attemptLoad);
            Assert.DoesNotContain("[&result]", attemptLoad);
            Assert.DoesNotContain("CompanionLoadAttemptResult result = CompanionLoadAttemptResult::LoadFailed;", attemptLoad);
        }

        [Fact]
        public void CompanionLoad_UnexpectedExceptionsKeepDistinctDiagnostic()
        {
            var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");
            var notSafeBranch = ExtractSwitchCase(
                companionLoad,
                "case CompanionLoadAttemptResult::NotSafeYet:",
                "case CompanionLoadAttemptResult::LoadFailed:");

            Assert.Contains("struct CompanionLoadAttempt", source);
            Assert.Contains("unexpected exception", source);
            Assert.Contains("unexpected non-standard exception", source);
            Assert.Contains("managed companion load deferred; dispatcher busy: Rhino command is active", source);
            Assert.Contains("attempt.diagnostic", notSafeBranch);
            Assert.DoesNotContain("managed companion load deferred; Rhino command is active", notSafeBranch);
        }

        [Fact]
        public void CompanionLoad_LoadFailureBudgetCountsOnlyActualLoadPlugInAttempts()
        {
            var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");

            Assert.Contains("int loadFailures = 0;", companionLoad);
            Assert.Contains("++loadFailures;", companionLoad);
            Assert.True(
                companionLoad.IndexOf("case CompanionLoadAttemptResult::LoadFailed:", StringComparison.Ordinal)
                < companionLoad.IndexOf("++loadFailures;", StringComparison.Ordinal),
                "The failure counter must only increment in the LoadFailed branch.");
            Assert.DoesNotContain("for (int attempt = 0; attempt < kLoadRetries; ++attempt)", companionLoad);
        }

        [Fact]
        public void CompanionLoad_HasStartupDeadlineAfterInitialDelay()
        {
            var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");

            Assert.Contains("kCompanionLoadStartupWindowMs", source);
            Assert.Contains("startupDeadline", companionLoad);
            Assert.True(
                companionLoad.IndexOf("std::this_thread::sleep_for(std::chrono::milliseconds(kInitialDelayMs));", StringComparison.Ordinal)
                < companionLoad.IndexOf("startupDeadline", StringComparison.Ordinal),
                "The startup deadline must begin after the initial delay.");
        }

        [Fact]
        public void CompanionLoad_ChecksAlreadyReadyBeforeAndInsideDispatch()
        {
            var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var attemptLoad = ExtractFunction(source, "AttemptCompanionLoadOnMainThread");

            Assert.Contains("if (Rook::Handlers::HasGrasshopperBridgeRegistration())", attemptLoad);
            Assert.Contains("CompanionLoadAttemptResult::AlreadyReady", attemptLoad);
            Assert.True(
                attemptLoad.IndexOf("if (Rook::Handlers::HasGrasshopperBridgeRegistration())", StringComparison.Ordinal)
                < attemptLoad.IndexOf("auto scheduled = CMainThreadDispatcher::Instance().Dispatch([", StringComparison.Ordinal),
                "AlreadyReady must be checked before dispatch.");
            Assert.True(
                attemptLoad.LastIndexOf("if (Rook::Handlers::HasGrasshopperBridgeRegistration())", StringComparison.Ordinal)
                > attemptLoad.IndexOf("auto scheduled = CMainThreadDispatcher::Instance().Dispatch([", StringComparison.Ordinal),
                "AlreadyReady must also be checked inside the dispatched lambda.");
        }

        [Fact]
        public void CompanionLoad_WritesNonDispatchDiagnosticsForCommandActiveDeferrals()
        {
            var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");

            Assert.Contains("ResolveCompanionLoadDiagnosticPath", source);
            Assert.Contains("companion-load-", source);
            Assert.Contains("OutputDebugStringW", source);

            var notSafeBranch = ExtractSwitchCase(
                companionLoad,
                "case CompanionLoadAttemptResult::NotSafeYet:",
                "case CompanionLoadAttemptResult::LoadFailed:");
            Assert.Contains("WriteCompanionLoadDiagnostic", notSafeBranch);
            Assert.DoesNotContain("RhinoApp().Print", notSafeBranch);
            Assert.DoesNotContain("CMainThreadDispatcher::Instance().Dispatch", notSafeBranch);
        }

        [Fact]
        public void SuspendGuard_RaiiClassIsNonCopyableAndTogglesDepth()
        {
            var header = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
            var raii = ExtractStruct(header.Replace("class DispatchDrainSuspension", "struct DispatchDrainSuspension"),
                                     "DispatchDrainSuspension");

            Assert.Contains("BeginSuspendGuard()", raii);
            Assert.Contains("EndSuspendGuard()", raii);
            Assert.Contains("DispatchDrainSuspension(const DispatchDrainSuspension&) = delete;", raii);
            Assert.Contains("DispatchDrainSuspension& operator=(const DispatchDrainSuspension&) = delete;", raii);
        }

        [Fact]
        public void BeginSuspendGuard_IncrementsDepth()
        {
            var header = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
            Assert.Contains("void BeginSuspendGuard() { m_suspendDepth.fetch_add(1, std::memory_order_release); }", header);
        }

        [Fact]
        public void EndSuspendGuard_PostsOnlyWhenSuspendDepthReleasesToZero()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
            var fn = ExtractFunction(source, "CMainThreadDispatcher::EndSuspendGuard");

            Assert.Contains("shouldPostDispatch = (current == 1);", fn);
            Assert.Contains("PostMessage(m_subclassedHwnd, WM_ROOK_DISPATCH", fn);
            Assert.Contains("compare_exchange_weak", fn);
        }

        [Fact]
        public void Dispatch_DoesNotConsultSuspendStateWhenEnqueueing()
        {
            // Enqueue must stay allowed while suspended: only draining is deferred.
            var header = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
            var dispatch = ExtractFunction(header, "CMainThreadDispatcher::Dispatch");

            Assert.DoesNotContain("IsAllDispatchBlocked", dispatch);
            Assert.DoesNotContain("IsDispatchSuspended", dispatch);
            Assert.DoesNotContain("m_suspendDepth", dispatch);
        }

        [Fact]
        public void Dispatcher_DeclaresSuspendDepthDistinctFromSaveDepth()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");

            Assert.Contains("std::atomic<int>  m_suspendDepth{0};", source);
            // Save depth still exists and is a separate field.
            Assert.Contains("std::atomic<int>  m_saveDepth{0};", source);
        }

        [Fact]
        public void IsAllDispatchBlocked_ChecksSaveOrSuspendDepth()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
            var fn = ExtractFunction(source, "CMainThreadDispatcher::IsAllDispatchBlocked");

            Assert.Contains("m_saveDepth.load(std::memory_order_acquire) > 0", fn);
            Assert.Contains("m_suspendDepth.load(std::memory_order_acquire) > 0", fn);
            Assert.Contains("||", fn);
        }

        private static string ExtractSwitchCase(string source, string caseStart, string nextCaseStart)
        {
            var start = source.IndexOf(caseStart, StringComparison.Ordinal);
            if (start < 0)
                throw new InvalidOperationException("Switch case not found: " + caseStart);

            var end = source.IndexOf(nextCaseStart, start + caseStart.Length, StringComparison.Ordinal);
            if (end < 0)
                throw new InvalidOperationException("Next switch case not found: " + nextCaseStart);

            return source.Substring(start, end - start);
        }

        private static string ExtractFunction(string source, string functionName)
        {
            var signatureStart = source.IndexOf(functionName + "(", StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Function not found: " + functionName);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Function body not found: " + functionName);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(signatureStart, i - signatureStart + 1);
                }
            }

            throw new InvalidOperationException("Function body did not close: " + functionName);
        }

        private static string ExtractStruct(string source, string structName)
        {
            var signatureStart = source.IndexOf("struct " + structName, StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Struct not found: " + structName);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Struct body not found: " + structName);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(signatureStart, i - signatureStart + 1);
                }
            }

            throw new InvalidOperationException("Struct body did not close: " + structName);
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
    }
}
