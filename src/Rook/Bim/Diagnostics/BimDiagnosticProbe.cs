using System;

namespace Rook.Bim
{
    public readonly struct BimAuxiliaryProbeResult<T>
    {
        private BimAuxiliaryProbeResult(bool known, T value)
        {
            Known = known;
            Value = value;
        }

        public bool Known { get; }

        public T Value { get; }

        internal static BimAuxiliaryProbeResult<T> FromValue(T value)
        {
            return new BimAuxiliaryProbeResult<T>(true, value);
        }

        internal static BimAuxiliaryProbeResult<T> Unknown
        {
            get { return new BimAuxiliaryProbeResult<T>(false, default!); }
        }
    }

    public static class BimDiagnosticProbe
    {
        public static T Production<T>(
            BimDiagnosticContext context,
            BimDiagnosticStage stage,
            Func<T> read,
            BimDiagnosticFields fields,
            Func<T, BimDiagnosticDetailCode>? detail = null)
        {
            if (context == null)
            {
                throw new ArgumentNullException(nameof(context));
            }

            if (read == null)
            {
                throw new ArgumentNullException(nameof(read));
            }

            if (!context.Enabled)
            {
                return read();
            }

            BimDiagnostics.Observe(
                context, stage, BimDiagnosticOutcome.Start, fields);
            T value;
            try
            {
                value = read();
            }
            catch (Exception exception)
            {
                BimDiagnostics.ObserveException(
                    context,
                    stage,
                    exception,
                    WithImpact(fields, BimDiagnosticFailureImpact.Production));
                throw;
            }

            BimDiagnostics.Observe(
                context,
                stage,
                BimDiagnosticOutcome.Success,
                WithDetail(fields, SelectDetail(detail, value)));
            return value;
        }

        public static BimAuxiliaryProbeResult<T> Auxiliary<T>(
            BimDiagnosticContext context,
            BimDiagnosticStage stage,
            Func<T> read,
            Func<T, BimDiagnosticDetailCode>? detail = null)
        {
            if (context == null)
            {
                throw new ArgumentNullException(nameof(context));
            }

            if (!context.Enabled)
            {
                return BimAuxiliaryProbeResult<T>.Unknown;
            }

            if (read == null)
            {
                throw new ArgumentNullException(nameof(read));
            }

            var fields = new BimDiagnosticFields(
                BimDiagnosticDetailCode.None,
                null,
                BimDiagnosticFailureImpact.Auxiliary);
            BimDiagnostics.Observe(
                context, stage, BimDiagnosticOutcome.Start, fields);
            T value;
            try
            {
                value = read();
            }
            catch (Exception exception)
            {
                BimDiagnostics.ObserveException(
                    context,
                    stage,
                    exception,
                    new BimDiagnosticFields(
                        BimDiagnosticDetailCode.ProbeFailure,
                        null,
                        BimDiagnosticFailureImpact.Auxiliary));
                return BimAuxiliaryProbeResult<T>.Unknown;
            }

            BimDiagnostics.Observe(
                context,
                stage,
                BimDiagnosticOutcome.Success,
                WithDetail(fields, SelectDetail(detail, value)));
            return BimAuxiliaryProbeResult<T>.FromValue(value);
        }

        private static BimDiagnosticDetailCode SelectDetail<T>(
            Func<T, BimDiagnosticDetailCode>? selector,
            T value)
        {
            if (selector == null)
            {
                return BimDiagnosticDetailCode.None;
            }

            try
            {
                var result = selector(value);
                BimDiagnosticContracts.ValidateDetailCode(result);
                return result;
            }
            catch
            {
                return BimDiagnosticDetailCode.None;
            }
        }

        private static BimDiagnosticFields WithDetail(
            BimDiagnosticFields fields,
            BimDiagnosticDetailCode detail)
        {
            return new BimDiagnosticFields(
                detail, fields.ItemIndex, fields.FailureImpact);
        }

        private static BimDiagnosticFields WithImpact(
            BimDiagnosticFields fields,
            BimDiagnosticFailureImpact impact)
        {
            return new BimDiagnosticFields(
                fields.DetailCode, fields.ItemIndex, impact);
        }
    }
}
