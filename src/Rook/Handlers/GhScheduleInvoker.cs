using System;
using System.Reflection;

namespace Rook.Handlers
{
    internal static class GhScheduleInvoker
    {
        public static GhScheduleResult Invoke(object document, GhScheduleDecision decision, int delayMs)
        {
            if (!decision.AttemptSchedule)
                return Result(decision, GhScheduleAcceptance.NotAttempted, null, decision.VerificationDeferred, null, decision.Warnings);
            if (delayMs <= 0)
                return Result(decision, GhScheduleAcceptance.NotAttempted, GhScheduleFailureCode.SchedulePreconditionRejected, decision.VerificationDeferred, null, decision.Warnings);

            MethodInfo? schedule;
            try
            {
                schedule = ResolveScheduleMethod(document.GetType());
            }
            catch (AmbiguousMatchException)
            {
                return Result(decision, GhScheduleAcceptance.NotAttempted, GhScheduleFailureCode.SchedulePreconditionRejected, decision.VerificationDeferred, null, decision.Warnings);
            }
            catch (Exception exception)
            {
                return Result(decision, GhScheduleAcceptance.Unknown, GhScheduleFailureCode.ScheduleAcceptanceUnknown, true, exception.GetType().Name, Append(decision.Warnings, GhScheduleWarning.ScheduleInvocationUnknown));
            }

            if (schedule == null)
                return Result(decision, GhScheduleAcceptance.Unavailable, GhScheduleFailureCode.ScheduleApiUnavailable, decision.VerificationDeferred, null, decision.Warnings);

            try
            {
                schedule.Invoke(document, new object[] { delayMs });
                return Result(decision, GhScheduleAcceptance.Accepted, null, true, null, Append(decision.Warnings, GhScheduleWarning.CompletionUnverified));
            }
            catch (TargetInvocationException exception)
            {
                return Result(decision, GhScheduleAcceptance.Unknown, GhScheduleFailureCode.ScheduleAcceptanceUnknown, true, (exception.InnerException ?? exception).GetType().Name, Append(decision.Warnings, GhScheduleWarning.ScheduleInvocationUnknown));
            }
            catch (Exception exception)
            {
                return Result(decision, GhScheduleAcceptance.Unknown, GhScheduleFailureCode.ScheduleAcceptanceUnknown, true, exception.GetType().Name, Append(decision.Warnings, GhScheduleWarning.ScheduleInvocationUnknown));
            }
        }

        private static GhScheduleResult Result(GhScheduleDecision decision, GhScheduleAcceptance acceptance, GhScheduleFailureCode? failureCode, bool verificationDeferred, string? exceptionType, GhScheduleWarning[] warnings) =>
            new GhScheduleResult
            {
                ScheduleClassification = decision.ScheduleClassification,
                ScheduleAcceptance = acceptance,
                ScheduleFailureCode = failureCode,
                VerificationDeferred = verificationDeferred,
                SolverLocked = decision.SolverLocked,
                SolverStateKnown = decision.SolverStateKnown,
                ExceptionType = exceptionType,
                Warnings = warnings ?? Array.Empty<GhScheduleWarning>(),
            };

        private static MethodInfo? ResolveScheduleMethod(Type documentType)
        {
            MethodInfo? match = null;
            for (var type = documentType; type != null; type = type.BaseType)
            {
                var methods = type.GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.DeclaredOnly);
                foreach (var method in methods)
                {
                    if (method.Name != "ScheduleSolution") continue;
                    var parameters = method.GetParameters();
                    if (parameters.Length != 1 || parameters[0].ParameterType != typeof(int)) continue;
                    if (match != null) throw new AmbiguousMatchException();
                    match = method;
                }
            }
            return match;
        }

        private static GhScheduleWarning[] Append(GhScheduleWarning[] warnings, GhScheduleWarning warning)
        {
            var source = warnings ?? Array.Empty<GhScheduleWarning>();
            var result = new GhScheduleWarning[source.Length + 1];
            Array.Copy(source, result, source.Length);
            result[source.Length] = warning;
            return result;
        }
    }
}
