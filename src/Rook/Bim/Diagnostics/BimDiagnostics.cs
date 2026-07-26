using System;
using System.Threading;

namespace Rook.Bim
{
    public static class BimDiagnostics
    {
        private static BimDiagnosticSession session =
            new BimDiagnosticSession(false, null);

        public static void Observe(
            BimDiagnosticContext context,
            BimDiagnosticStage stage,
            BimDiagnosticOutcome outcome,
            BimDiagnosticFields fields)
        {
            Volatile.Read(ref session).Observe(context, stage, outcome, fields);
        }

        public static void ObserveException(
            BimDiagnosticContext context,
            BimDiagnosticStage stage,
            Exception exception,
            BimDiagnosticFields fields)
        {
            Volatile.Read(ref session).ObserveException(
                context, stage, exception, fields);
        }

        public static void CompleteRequest(
            BimDiagnosticContext context,
            BimDiagnosticOutcome routeOutcome)
        {
            Volatile.Read(ref session).CompleteRequest(context, routeOutcome);
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
            private readonly BimDiagnosticSession replacement;

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
                if (restore != null)
                {
                    Interlocked.CompareExchange(
                        ref session, restore, replacement);
                }
            }
        }
    }
}
