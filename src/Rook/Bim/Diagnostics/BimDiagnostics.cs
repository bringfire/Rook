using System;
using System.IO;
using System.Reflection;
using System.Threading;

namespace Rook.Bim
{
    internal sealed class BimDiagnosticProvenanceSnapshot
    {
        internal BimDiagnosticProvenanceSnapshot(
            string coreVersion,
            string coreCommit,
            string moduleVersion,
            string moduleCommit)
        {
            CoreVersion = coreVersion;
            CoreCommit = coreCommit;
            ModuleVersion = moduleVersion;
            ModuleCommit = moduleCommit;
        }

        internal string CoreVersion { get; }
        internal string CoreCommit { get; }
        internal string ModuleVersion { get; }
        internal string ModuleCommit { get; }
    }

    internal sealed class BimDiagnosticProvenance
    {
        private sealed class ModuleMetadata
        {
            internal ModuleMetadata(string version, string commit)
            {
                Version = version;
                Commit = commit;
            }

            internal string Version { get; }
            internal string Commit { get; }
        }

        private readonly string coreVersion;
        private readonly string coreCommit;
        private ModuleMetadata module = new ModuleMetadata(
            "unavailable", "unavailable");

        internal BimDiagnosticProvenance(Assembly coreAssembly)
        {
            if (coreAssembly == null)
            {
                throw new ArgumentNullException(nameof(coreAssembly));
            }

            coreVersion = ReadVersion(coreAssembly);
            coreCommit = ReadCommit(coreAssembly);
        }

        internal void RegisterModule(Assembly assembly)
        {
            if (assembly == null)
            {
                throw new ArgumentNullException(nameof(assembly));
            }

            Interlocked.Exchange(ref module, new ModuleMetadata(
                ReadVersion(assembly), ReadCommit(assembly)));
        }

        internal BimDiagnosticProvenanceSnapshot Snapshot()
        {
            var currentModule = Volatile.Read(ref module);
            return new BimDiagnosticProvenanceSnapshot(
                coreVersion,
                coreCommit,
                currentModule.Version,
                currentModule.Commit);
        }

        private static string ReadVersion(Assembly assembly)
        {
            try
            {
                var value = assembly.GetName().Version?.ToString();
                return string.IsNullOrEmpty(value)
                    ? "unavailable"
                    : BimDiagnosticContracts.BoundProvenance(value);
            }
            catch (Exception)
            {
                return "unavailable";
            }
        }

        private static string ReadCommit(Assembly assembly)
        {
            try
            {
                var informational = assembly
                    .GetCustomAttribute<AssemblyInformationalVersionAttribute>()
                    ?.InformationalVersion;
                if (string.IsNullOrEmpty(informational))
                {
                    return "unavailable";
                }

                var separator = informational!.LastIndexOf('+');
                if (separator < 0 || separator == informational.Length - 1)
                {
                    return "unavailable";
                }

                var suffix = informational.Substring(separator + 1);
                for (var index = 0; index < suffix.Length; index++)
                {
                    var character = suffix[index];
                    var hexadecimal = character >= '0' && character <= '9' ||
                        character >= 'a' && character <= 'f' ||
                        character >= 'A' && character <= 'F';
                    if (!hexadecimal)
                    {
                        return "unavailable";
                    }
                }

                return BimDiagnosticContracts.BoundProvenance(suffix);
            }
            catch (Exception)
            {
                return "unavailable";
            }
        }
    }

    internal sealed class BimDiagnosticBootstrap
    {
        internal const string EnvironmentVariableName = "ROOK_BIM_DIAGNOSTICS";

        private readonly object sync = new object();
        private readonly Func<string, string?> environmentReader;
        private readonly Func<BimDiagnosticProvenance,
            IBimDiagnosticEnvelopeSink> sinkFactory;
        private readonly BimDiagnosticProvenance provenance;
        private BimDiagnosticSession session;
        private int initialized;

        internal BimDiagnosticBootstrap(
            Func<string, string?> environmentReader,
            Func<BimDiagnosticProvenance, IBimDiagnosticEnvelopeSink> sinkFactory,
            Assembly coreAssembly)
        {
            this.environmentReader = environmentReader ??
                throw new ArgumentNullException(nameof(environmentReader));
            this.sinkFactory = sinkFactory ??
                throw new ArgumentNullException(nameof(sinkFactory));
            provenance = new BimDiagnosticProvenance(coreAssembly);
            session = new BimDiagnosticSession(false, null, provenance);
        }

        internal BimDiagnosticSession CurrentSession
        {
            get { return Volatile.Read(ref session); }
        }

        internal BimDiagnosticSession Initialize()
        {
            if (Volatile.Read(ref initialized) != 0)
            {
                return CurrentSession;
            }

            lock (sync)
            {
                if (initialized != 0)
                {
                    return session;
                }

                var enabled = false;
                try
                {
                    enabled = string.Equals(
                        environmentReader(EnvironmentVariableName),
                        "1",
                        StringComparison.Ordinal);
                }
                catch (Exception)
                {
                }

                IBimDiagnosticEnvelopeSink? sink = null;
                var sinkFactoryFailed = false;
                if (enabled)
                {
                    try
                    {
                        sink = sinkFactory(provenance);
                    }
                    catch (Exception)
                    {
                        sink = new FailedBimDiagnosticSink(
                            BimDiagnosticSinkFailureCode.FileOpenFailure);
                        sinkFactoryFailed = true;
                    }
                }

                var created = new BimDiagnosticSession(enabled, sink, provenance);
                Volatile.Write(ref session, created);
                Volatile.Write(ref initialized, 1);

                if (enabled)
                {
                    var context = created.CreateUncorrelatedContext("initialize");
                    if (sinkFactoryFailed)
                    {
                        created.Observe(context,
                            BimDiagnosticStage.CoreInitialize,
                            BimDiagnosticOutcome.Failure,
                            BimDiagnosticFields.None);
                    }
                    else
                    {
                        created.Observe(context,
                            BimDiagnosticStage.CoreInitialize,
                            BimDiagnosticOutcome.Start,
                            BimDiagnosticFields.None);
                        if (sink is BimDiagnosticSink boundedSink)
                        {
                            boundedSink.Start();
                        }

                        created.Observe(context,
                            BimDiagnosticStage.CoreInitialize,
                            BimDiagnosticOutcome.Success,
                            BimDiagnosticFields.None);
                    }
                }

                return created;
            }
        }

        internal void RegisterModuleMetadata(Assembly assembly)
        {
            CurrentSession.RegisterModuleMetadata(assembly);
        }

        internal BimDiagnosticStatusSnapshot SnapshotStatus()
        {
            return CurrentSession.SnapshotStatus();
        }
    }

    public static class BimDiagnostics
    {
        private static readonly BimDiagnosticBootstrap bootstrap =
            new BimDiagnosticBootstrap(
                Environment.GetEnvironmentVariable,
                provenance => new BimDiagnosticSink(
                    Path.Combine(
                        Environment.GetFolderPath(
                            Environment.SpecialFolder.LocalApplicationData),
                        "Rook",
                        "diagnostics"),
                    provenance),
                typeof(BimDiagnostics).Assembly);

        private static BimDiagnosticSession session = bootstrap.CurrentSession;

        public static void InitializeFromEnvironment()
        {
            try
            {
                Volatile.Write(ref session, bootstrap.Initialize());
            }
            catch (Exception)
            {
            }
        }

        public static BimDiagnosticContext CreateContext(string operation)
        {
            try
            {
                return Volatile.Read(ref session).CreateContext(operation);
            }
            catch (Exception)
            {
                return BimDiagnosticContext.Disabled;
            }
        }

        internal static BimDiagnosticContext CreateUncorrelatedContext(
            string operation)
        {
            try
            {
                return Volatile.Read(ref session)
                    .CreateUncorrelatedContext(operation);
            }
            catch (Exception)
            {
                return BimDiagnosticContext.Disabled;
            }
        }

        public static void RegisterModuleMetadata(Assembly assembly)
        {
            try
            {
                Volatile.Read(ref session).RegisterModuleMetadata(assembly);
            }
            catch (Exception)
            {
            }
        }

        public static BimDiagnosticRequestSnapshot SnapshotRequest(
            BimDiagnosticContext context)
        {
            try
            {
                return Volatile.Read(ref session).SnapshotRequest(context);
            }
            catch (Exception)
            {
                return new BimDiagnosticRequestSnapshot(
                    null, null, null, null, null, null, 0);
            }
        }

        public static BimDiagnosticStatusSnapshot SnapshotStatus()
        {
            try
            {
                return Volatile.Read(ref session).SnapshotStatus();
            }
            catch (Exception)
            {
                try
                {
                    return bootstrap.SnapshotStatus();
                }
                catch (Exception)
                {
                    return new BimDiagnosticStatusSnapshot(
                        false,
                        BimDiagnosticSinkState.Disabled,
                        BimDiagnosticSinkFailureCode.None,
                        0,
                        "unavailable",
                        "unavailable",
                        "unavailable",
                        "unavailable");
                }
            }
        }

        public static void Observe(
            BimDiagnosticContext context,
            BimDiagnosticStage stage,
            BimDiagnosticOutcome outcome,
            BimDiagnosticFields fields)
        {
            var current = Volatile.Read(ref session);
            try
            {
                current.Observe(context, stage, outcome, fields);
            }
            catch (ArgumentException)
            {
                current.RecordInvalid(context);
            }
            catch (Exception)
            {
            }
        }

        public static void ObserveException(
            BimDiagnosticContext context,
            BimDiagnosticStage stage,
            Exception exception,
            BimDiagnosticFields fields)
        {
            var current = Volatile.Read(ref session);
            try
            {
                current.ObserveException(
                    context, stage, exception, fields);
            }
            catch (ArgumentException)
            {
                current.RecordInvalid(context);
            }
            catch (Exception)
            {
            }
        }

        public static void CompleteRequest(
            BimDiagnosticContext context,
            BimDiagnosticOutcome routeOutcome)
        {
            try
            {
                Volatile.Read(ref session).CompleteRequest(context, routeOutcome);
            }
            catch (Exception)
            {
            }
        }

        internal static IDisposable PushSessionForTests(
            BimDiagnosticSession replacement)
        {
            if (replacement == null)
            {
                throw new ArgumentNullException(nameof(replacement));
            }

            var previous = Interlocked.Exchange(ref session, replacement);
            return new SessionScope(previous, replacement);
        }

        private sealed class SessionScope : IDisposable
        {
            private BimDiagnosticSession? previous;
            private BimDiagnosticSession? replacement;

            internal SessionScope(
                BimDiagnosticSession previous,
                BimDiagnosticSession replacement)
            {
                this.previous = previous;
                this.replacement = replacement;
            }

            public void Dispose()
            {
                var restore = Interlocked.Exchange(ref previous, null);
                var toStop = Interlocked.Exchange(ref replacement, null);
                if (restore != null && toStop != null)
                {
                    Interlocked.CompareExchange(ref session, restore, toStop);
                    toStop.Stop();
                }
            }
        }
    }
}
