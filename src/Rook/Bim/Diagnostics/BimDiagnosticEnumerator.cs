using System;
using System.Collections;

namespace Rook.Bim
{
    public static class BimDiagnosticEnumerator
    {
        public static void ForEach<T>(
            BimDiagnosticContext context,
            IEnumerable source,
            Action<T, long> visitor)
        {
            if (context == null)
            {
                throw new ArgumentNullException(nameof(context));
            }

            if (source == null)
            {
                throw new ArgumentNullException(nameof(source));
            }

            if (visitor == null)
            {
                throw new ArgumentNullException(nameof(visitor));
            }

            if (!context.Enabled)
            {
                ForEachDisabled(source, visitor);
                return;
            }

            var iterator = BimDiagnosticProbe.Production(
                context,
                BimDiagnosticStage.RevitCategoriesIterator,
                source.GetEnumerator,
                BimDiagnosticFields.None);
            try
            {
                long index = 0;
                while (BimDiagnosticProbe.Production(
                    context,
                    BimDiagnosticStage.RevitCategoriesMoveNext,
                    iterator.MoveNext,
                    BimDiagnosticFields.None,
                    moved => moved
                        ? BimDiagnosticDetailCode.True
                        : BimDiagnosticDetailCode.False))
                {
                    var currentIndex = index;
                    var current = BimDiagnosticProbe.Production(
                        context,
                        BimDiagnosticStage.RevitCategoriesCurrent,
                        () => (T)iterator.Current,
                        new BimDiagnosticFields(
                            BimDiagnosticDetailCode.None,
                            currentIndex,
                            BimDiagnosticFailureImpact.Production));
                    visitor(current, currentIndex);
                    index++;
                }
            }
            finally
            {
                if (iterator is IDisposable disposable)
                {
                    BimDiagnosticProbe.Production(
                        context,
                        BimDiagnosticStage.RevitCategoriesIteratorDispose,
                        () =>
                        {
                            disposable.Dispose();
                            return true;
                        },
                        BimDiagnosticFields.None);
                }
                else
                {
                    BimDiagnostics.Observe(
                        context,
                        BimDiagnosticStage.RevitCategoriesIteratorDispose,
                        BimDiagnosticOutcome.Success,
                        new BimDiagnosticFields(
                            BimDiagnosticDetailCode.NotDisposable,
                            null,
                            BimDiagnosticFailureImpact.None));
                }
            }
        }

        private static void ForEachDisabled<T>(
            IEnumerable source,
            Action<T, long> visitor)
        {
            var iterator = source.GetEnumerator();
            try
            {
                long index = 0;
                while (iterator.MoveNext())
                {
                    var current = (T)iterator.Current;
                    visitor(current, index);
                    index++;
                }
            }
            finally
            {
                if (iterator is IDisposable disposable)
                {
                    disposable.Dispose();
                }
            }
        }
    }
}
