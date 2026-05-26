using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Threading
{
    public class MainThreadDispatcherSourceTests
    {
        [Fact]
        public void DrainQueue_BlocksAllDispatchDuringSave()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
            var drainQueue = ExtractFunction(source, "CMainThreadDispatcher::DrainQueue");

            Assert.Contains("IsAllDispatchBlocked()", drainQueue);
            Assert.DoesNotContain("IsCommandActive()", ExtractFunction(source, "CMainThreadDispatcher::EndSaveGuard"));
        }

        [Fact]
        public void DrainQueue_DefersNormalTasksInOriginalRelativeOrderWhileCommandActive()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
            var drainQueue = ExtractFunction(source, "CMainThreadDispatcher::DrainQueue");

            Assert.Contains("IsNormalDispatchBlocked()", drainQueue);
            Assert.Contains("std::queue<QueuedTask> deferred", drainQueue);
            Assert.Contains("queued.policy == DispatchPolicy::CommandControl", drainQueue);
            Assert.Contains("deferred.push(std::move(queued));", drainQueue);
            Assert.Contains("std::swap(m_queue, deferred);", drainQueue);
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
