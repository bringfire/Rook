using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace Rook.Services.Vision.Video.Framing
{
    internal sealed class FramingNativeHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        public FramingNativeHandle(IntPtr handle) : base(true) { SetHandle(handle); }
        protected override bool ReleaseHandle() => WindowsFramingJobNative.CloseHandle(handle);
    }

    // The virtual boundary permits fail-closed policies to be exercised without
    // changing the process launcher or substituting an uncontained launcher.
    internal class WindowsFramingJobNative
    {
        internal virtual void ConfigureJob(FramingNativeHandle job, FramingNativeHandle completion)
        {
            SetInfo(job, 7, new AssociateCompletion { CompletionKey = new IntPtr(1), CompletionPort = completion.DangerousGetHandle() });
            SetInfo(job, 9, new ExtendedLimits {
                Basic = new BasicLimits { LimitFlags = 0x200 | 0x2000 },
                JobMemoryLimit = new UIntPtr((ulong)VideoPreparationLimits.RendererCommitBytes)
            });
            SetInfo(job, 12, new NotificationLimits { LimitFlags = 0x200, JobMemoryLimit = 480UL * 1024 * 1024 });
            var installed = QueryLimits(job);
            if ((installed.Basic.LimitFlags & 0x2200) != 0x2200 ||
                installed.JobMemoryLimit.ToUInt64() != (ulong)VideoPreparationLimits.RendererCommitBytes)
                throw new Win32Exception("Renderer memory limits could not be verified.");
        }
        internal virtual void AssignProcess(FramingNativeHandle job, FramingNativeHandle process)
        { Check(AssignProcessToJobObject(job, process)); }
        internal virtual void ResumeProcess(FramingNativeHandle thread)
        { if (ResumeThread(thread) == uint.MaxValue) throw new Win32Exception(Marshal.GetLastWin32Error()); }
        internal static FramingNativeHandle CreateJob()
        { var handle = new FramingNativeHandle(CreateJobObjectW(IntPtr.Zero, null)); CheckHandle(handle); return handle; }
        internal static FramingNativeHandle CreateCompletionPort()
        { var handle = new FramingNativeHandle(CreateIoCompletionPort(new IntPtr(-1), IntPtr.Zero, UIntPtr.Zero, 1)); CheckHandle(handle); return handle; }
        internal static void Terminate(FramingNativeHandle job) { if (!job.IsClosed && !job.IsInvalid) TerminateJobObject(job, 137); }
        internal static long PeakCommit(FramingNativeHandle job) => checked((long)QueryLimits(job).PeakJobMemoryUsed.ToUInt64());
        internal static void ReadViolation(FramingNativeHandle job)
        {
            var info = new byte[80];
            Check(QueryInformationJobObject(job, 13, info, info.Length, IntPtr.Zero));
        }
        private static ExtendedLimits QueryLimits(FramingNativeHandle job)
        {
            int size = Marshal.SizeOf<ExtendedLimits>();
            var memory = Marshal.AllocHGlobal(size);
            try
            {
                Check(QueryInformationJobObjectPointer(job, 9, memory, size, IntPtr.Zero));
                return Marshal.PtrToStructure<ExtendedLimits>(memory);
            }
            finally { Marshal.FreeHGlobal(memory); }
        }
        private static void SetInfo<T>(FramingNativeHandle job, int type, T value) where T : struct
        {
            int size = Marshal.SizeOf<T>(); var memory = Marshal.AllocHGlobal(size);
            try { Marshal.StructureToPtr(value, memory, false); Check(SetInformationJobObject(job, type, memory, size)); }
            finally { Marshal.FreeHGlobal(memory); }
        }
        internal static SuspendedFramingProcess CreateSuspended(FramingProcessRequest request)
        {
            var security = new SecurityAttributes { Length = Marshal.SizeOf<SecurityAttributes>(), InheritHandle = true };
            var input = Pipe(ref security);
            using var inputRead = input.Read; using var inputWrite = input.Write;
            var output = Pipe(ref security);
            using var outputWrite = output.Write; using var outputRead = output.Read;
            var error = Pipe(ref security);
            using var errorWrite = error.Write; using var errorRead = error.Read;
            Check(SetHandleInformation(outputRead, 1, 0));
            Check(SetHandleInformation(errorRead, 1, 0));
            Check(SetHandleInformation(inputWrite, 1, 0));
            IntPtr attributeSize = IntPtr.Zero;
            InitializeProcThreadAttributeList(IntPtr.Zero, 1, 0, ref attributeSize);
            if (attributeSize == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            var attributeList = Marshal.AllocHGlobal(attributeSize);
            var handles = Marshal.AllocHGlobal(IntPtr.Size * 3);
            bool initialized = false;
            ProcessInformation process = default;
            try
            {
                Check(InitializeProcThreadAttributeList(attributeList, 1, 0, ref attributeSize)); initialized = true;
                Marshal.WriteIntPtr(handles, 0, inputRead.DangerousGetHandle());
                Marshal.WriteIntPtr(handles, IntPtr.Size, outputWrite.DangerousGetHandle());
                Marshal.WriteIntPtr(handles, IntPtr.Size * 2, errorWrite.DangerousGetHandle());
                Check(UpdateProcThreadAttribute(attributeList, 0, new IntPtr(0x20002), handles, new IntPtr(IntPtr.Size * 3), IntPtr.Zero, IntPtr.Zero));
                var start = new StartupInfoEx {
                    Startup = new StartupInfo {
                        Size = Marshal.SizeOf<StartupInfoEx>(), Flags = 0x100,
                        StdInput = inputRead.DangerousGetHandle(), StdOutput = outputWrite.DangerousGetHandle(),
                        StdError = errorWrite.DangerousGetHandle()
                    }, Attributes = attributeList
                };
                var command = new StringBuilder(QuoteArgument(request.ExecutablePath));
                foreach (var argument in request.Arguments) command.Append(' ').Append(QuoteArgument(argument));
                Check(CreateProcessW(request.ExecutablePath, command, IntPtr.Zero, IntPtr.Zero, true,
                    0x4 | 0x08000000 | 0x00080000, IntPtr.Zero, request.WorkingDirectory, ref start, out process));
                var processHandle = new FramingNativeHandle(process.Process);
                var threadHandle = new FramingNativeHandle(process.Thread);
                process = default; // ownership transferred
                FileStream? stdout = null;
                try { stdout = TakeReadStream(outputRead); return new SuspendedFramingProcess(processHandle, threadHandle, stdout, TakeReadStream(errorRead)); }
                catch { stdout?.Dispose(); TerminateProcess(processHandle, 137); processHandle.Dispose(); threadHandle.Dispose(); throw; }
            }
            finally
            {
                if (process.Process != IntPtr.Zero) { TerminateProcessRaw(process.Process, 137); CloseHandle(process.Process); CloseHandle(process.Thread); }
                if (initialized) DeleteProcThreadAttributeList(attributeList);
                Marshal.FreeHGlobal(handles); Marshal.FreeHGlobal(attributeList);
            }
        }
        private static FileStream TakeReadStream(FramingNativeHandle source)
        {
            var handle = new SafeFileHandle(source.DangerousGetHandle(), true);
            source.SetHandleAsInvalid();
            try { return new FileStream(handle, FileAccess.Read, 4096, false); }
            catch { handle.Dispose(); throw; }
        }
        private static (FramingNativeHandle Read, FramingNativeHandle Write) Pipe(ref SecurityAttributes security)
        { Check(CreatePipe(out var read, out var write, ref security, 0)); return (new(read), new(write)); }
        internal static string QuoteArgument(string value)
        {
            if (value.IndexOf('\0') >= 0) throw new ArgumentException("Invalid process argument.");
            var output = new StringBuilder("\""); int slashes = 0;
            foreach (char c in value)
            {
                if (c == '\\') { slashes++; continue; }
                if (c == '"') { output.Append('\\', slashes * 2 + 1).Append('"'); slashes = 0; continue; }
                output.Append('\\', slashes).Append(c); slashes = 0;
            }
            return output.Append('\\', slashes * 2).Append('"').ToString();
        }
        private static void Check(bool success) { if (!success) throw new Win32Exception(Marshal.GetLastWin32Error()); }
        private static void CheckHandle(FramingNativeHandle handle)
        { if (handle.IsInvalid) { int error = Marshal.GetLastWin32Error(); handle.Dispose(); throw new Win32Exception(error); } }

        [StructLayout(LayoutKind.Sequential)] private struct SecurityAttributes { public int Length; public IntPtr Descriptor; [MarshalAs(UnmanagedType.Bool)] public bool InheritHandle; }
        [StructLayout(LayoutKind.Sequential)] private struct BasicLimits
        { public long ProcessTime, JobTime; public uint LimitFlags; public UIntPtr MinWorking, MaxWorking; public uint ActiveProcesses; public UIntPtr Affinity; public uint Priority, Scheduling; }
        [StructLayout(LayoutKind.Sequential)] private struct IoCounters { public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }
        [StructLayout(LayoutKind.Sequential)] private struct ExtendedLimits
        { public BasicLimits Basic; public IoCounters Io; public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed; }
        [StructLayout(LayoutKind.Sequential)] private struct NotificationLimits
        { public ulong ReadBytes, WriteBytes; public long JobTime; public ulong JobMemoryLimit; public uint Tolerance, Interval, LimitFlags; }
        [StructLayout(LayoutKind.Sequential)] private struct AssociateCompletion { public IntPtr CompletionKey, CompletionPort; }
        [StructLayout(LayoutKind.Sequential)] private struct StartupInfo
        {
            public int Size; public IntPtr Reserved, Desktop, Title;
            public int X, Y, XSize, YSize, XCount, YCount, Fill; public uint Flags;
            public ushort ShowWindow, ReservedSize; public IntPtr ReservedBytes, StdInput, StdOutput, StdError;
        }
        [StructLayout(LayoutKind.Sequential)] private struct StartupInfoEx { public StartupInfo Startup; public IntPtr Attributes; }
        [StructLayout(LayoutKind.Sequential)] private struct ProcessInformation { public IntPtr Process, Thread; public uint ProcessId, ThreadId; }

        [DllImport("kernel32", SetLastError = true)] internal static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] private static extern IntPtr CreateJobObjectW(IntPtr security, string? name);
        [DllImport("kernel32", SetLastError = true)] private static extern bool SetInformationJobObject(FramingNativeHandle job, int type, IntPtr info, int size);
        [DllImport("kernel32", SetLastError = true)] private static extern bool AssignProcessToJobObject(FramingNativeHandle job, FramingNativeHandle process);
        [DllImport("kernel32", SetLastError = true)] private static extern bool QueryInformationJobObject(FramingNativeHandle job, int type, [Out] byte[] data, int size, IntPtr returned);
        [DllImport("kernel32", EntryPoint = "QueryInformationJobObject", SetLastError = true)] private static extern bool QueryInformationJobObjectPointer(FramingNativeHandle job, int type, IntPtr data, int size, IntPtr returned);
        [DllImport("kernel32", SetLastError = true)] private static extern IntPtr CreateIoCompletionPort(IntPtr file, IntPtr port, UIntPtr key, uint concurrency);
        [DllImport("kernel32", SetLastError = true)] internal static extern bool GetQueuedCompletionStatus(FramingNativeHandle port, out uint code, out UIntPtr key, out IntPtr overlapped, uint milliseconds);
        [DllImport("kernel32", SetLastError = true)] private static extern bool TerminateJobObject(FramingNativeHandle job, uint exitCode);
        [DllImport("kernel32", SetLastError = true)] internal static extern bool TerminateProcess(FramingNativeHandle process, uint code);
        [DllImport("kernel32", EntryPoint = "TerminateProcess", SetLastError = true)] private static extern bool TerminateProcessRaw(IntPtr process, uint code);
        [DllImport("kernel32", SetLastError = true)] private static extern uint ResumeThread(FramingNativeHandle thread);
        [DllImport("kernel32", SetLastError = true)] internal static extern uint WaitForSingleObject(FramingNativeHandle handle, uint milliseconds);
        [DllImport("kernel32", SetLastError = true)] internal static extern bool GetExitCodeProcess(FramingNativeHandle process, out uint code);
        [DllImport("kernel32", SetLastError = true)] internal static extern uint GetProcessId(FramingNativeHandle process);
        [DllImport("kernel32", SetLastError = true)] private static extern bool CreatePipe(out IntPtr read, out IntPtr write, ref SecurityAttributes security, uint size);
        [DllImport("kernel32", SetLastError = true)] private static extern bool SetHandleInformation(FramingNativeHandle handle, uint mask, uint flags);
        [DllImport("kernel32", SetLastError = true)] private static extern bool InitializeProcThreadAttributeList(IntPtr list, int count, int flags, ref IntPtr size);
        [DllImport("kernel32", SetLastError = true)] private static extern bool UpdateProcThreadAttribute(IntPtr list, uint flags, IntPtr attribute, IntPtr value, IntPtr size, IntPtr previous, IntPtr returned);
        [DllImport("kernel32")] private static extern void DeleteProcThreadAttributeList(IntPtr list);
        [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CreateProcessW(string application, StringBuilder command, IntPtr processSecurity, IntPtr threadSecurity,
            bool inherit, uint flags, IntPtr environment, string directory, ref StartupInfoEx startup, out ProcessInformation information);
    }

    internal sealed class SuspendedFramingProcess : IDisposable
    {
        public FramingNativeHandle Process { get; }
        public FramingNativeHandle Thread { get; }
        public Stream Stdout { get; }
        public Stream Stderr { get; }
        public SuspendedFramingProcess(FramingNativeHandle process, FramingNativeHandle thread, Stream stdout, Stream stderr)
        { Process = process; Thread = thread; Stdout = stdout; Stderr = stderr; }
        public void Dispose()
        {
            if (!Process.IsClosed && WindowsFramingJobNative.WaitForSingleObject(Process, 0) == 258)
            { WindowsFramingJobNative.TerminateProcess(Process, 137); WindowsFramingJobNative.WaitForSingleObject(Process, 5000); }
            Stdout.Dispose(); Stderr.Dispose(); Thread.Dispose(); Process.Dispose();
        }
    }
}
