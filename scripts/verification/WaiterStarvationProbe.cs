using System;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;

// Runs in its own net48 process so thread-pool constraints cannot affect xUnit,
// Rhino, or another test. Invoke the real tests against the built assembly.
internal static class WaiterStarvationProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) throw new ArgumentException("Expected the built Rook.Tests.dll path.");
        string assemblyPath = Path.GetFullPath(args[0]);
        AppDomain.CurrentDomain.AssemblyResolve += delegate(object sender, ResolveEventArgs request) {
            string path = Path.Combine(Path.GetDirectoryName(assemblyPath), new AssemblyName(request.Name).Name + ".dll");
            return File.Exists(path) ? Assembly.LoadFrom(path) : null;
        };
        var type = Assembly.LoadFrom(assemblyPath).GetType("Rook.Tests.InternalBridge.GhSolveReceiptRegistryTests", true);
        int workers, io;
        ThreadPool.GetMaxThreads(out workers, out io);
        if (!ThreadPool.SetMinThreads(1, 1) || !ThreadPool.SetMaxThreads(1, io)) throw new Exception("Cannot constrain the isolated probe pool.");
        using (var entered = new ManualResetEvent(false))
        using (var release = new ManualResetEvent(false))
        using (var finished = new ManualResetEvent(false)) {
            ThreadPool.QueueUserWorkItem(delegate { entered.Set(); release.WaitOne(); finished.Set(); });
            if (!entered.WaitOne(10000)) throw new Exception("The pool blocker did not start.");
            try {
                string[] cases = {
                    "Supersession_SignalsPendingWaiterAndReleasesOwnership",
                    "Wait_BlocksUntilMatchingCompletionSignal",
                    "Wait_SecondPendingWaiter_IsRejectedWithoutTakingOwnership",
                    "ReplaceDocument_TombstonesReceiptAndSignalsWaiter",
                    "Wait_EvictedSignaledReceipt_ReturnsCapturedTerminalResult"
                };
                for (int repeat = 0; repeat < 20; repeat++)
                    foreach (string test in cases)
                        type.GetMethod(test).Invoke(Activator.CreateInstance(type), null);
                Console.WriteLine("PASS: 100 real registry scenarios with the sole pool worker occupied throughout.");
                // Exercise the real net48 bridge-timeout regression with pool
                // dispatch delayed beyond its 500ms budget. This specifically
                // covers token registration after the bridge disposes its CTS.
                var releaseThread = new Thread(delegate() { Thread.Sleep(2000); release.Set(); });
                releaseThread.IsBackground = true;
                releaseThread.Start();
                var imageType = type.Assembly.GetType("Rook.Tests.Handlers.ImageFallbackHandlerTests", true);
                var imageTask = (Task)imageType.GetMethod("NativeOuterTimeoutKeepsReceiptAndReturnsBeforeHeldTransport").Invoke(Activator.CreateInstance(imageType), null);
                try { imageTask.GetAwaiter().GetResult(); }
                finally { release.Set(); if (!releaseThread.Join(10000)) throw new Exception("The owned delayed-release thread did not stop."); }
                Console.WriteLine("PASS: real image bridge timeout/cancellation regression with delayed pool availability.");
                return 0;
            } catch (TargetInvocationException ex) {
                Console.Error.WriteLine(ex.InnerException);
                return 1;
            } finally {
                release.Set();
                if (!finished.WaitOne(10000)) throw new Exception("The owned pool blocker did not stop.");
                ThreadPool.SetMaxThreads(workers, io);
            }
        }
    }
}
