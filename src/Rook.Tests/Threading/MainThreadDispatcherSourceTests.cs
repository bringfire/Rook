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
