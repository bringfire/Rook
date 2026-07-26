using System;
using System.Collections.Generic;
using Rook.Bim;

namespace Rook.Tests.Bim.Diagnostics
{
    internal static class TestDiagnostics
    {
        internal static BimDiagnosticContext EnabledContext(string operation)
        {
            return BimDiagnosticContext.CreateEnabled(operation);
        }

        internal static TestDiagnosticScope EnabledScope(string operation)
        {
            var sink = new InMemoryBimDiagnosticEnvelopeSink();
            var session = new BimDiagnosticSession(true, sink);
            var context = session.CreateContext(operation);
            return new TestDiagnosticScope(
                session,
                context,
                sink,
                BimDiagnostics.PushSessionForTests(session));
        }

        internal static BimDiagnosticRequestSnapshot Snapshot(BimDiagnosticContext context)
        {
            if (context.Accumulator == null)
            {
                throw new InvalidOperationException("The test context is not enabled.");
            }

            return context.Accumulator.Snapshot();
        }
    }

    internal sealed class TestDiagnosticScope : IDisposable
    {
        private readonly IDisposable sessionRegistration;

        internal TestDiagnosticScope(
            BimDiagnosticSession session,
            BimDiagnosticContext context,
            InMemoryBimDiagnosticEnvelopeSink sink,
            IDisposable sessionRegistration)
        {
            Session = session;
            Context = context;
            Sink = sink;
            this.sessionRegistration = sessionRegistration;
        }

        internal BimDiagnosticSession Session { get; }

        internal BimDiagnosticContext Context { get; }

        internal InMemoryBimDiagnosticEnvelopeSink Sink { get; }

        public void Dispose()
        {
            sessionRegistration.Dispose();
        }
    }

    internal sealed class InMemoryBimDiagnosticEnvelopeSink : IBimDiagnosticEnvelopeSink
    {
        private readonly object sync = new object();
        private readonly List<BimDiagnosticEnvelope> envelopes =
            new List<BimDiagnosticEnvelope>();

        internal IReadOnlyList<BimDiagnosticEnvelope> Envelopes
        {
            get
            {
                lock (sync)
                {
                    return envelopes.ToArray();
                }
            }
        }

        public bool TryEnqueue(BimDiagnosticEnvelope envelope)
        {
            lock (sync)
            {
                envelopes.Add(envelope);
                return true;
            }
        }
    }
}
