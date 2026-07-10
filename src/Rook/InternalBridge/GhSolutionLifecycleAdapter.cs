using System;
using System.Linq.Expressions;
using System.Reflection;
using System.Threading;

namespace Rook.InternalBridge
{
    internal sealed class GhSolutionLifecycleAdapter
    {
        internal GhSolutionLifecycleSubscription Attach(
            object document,
            Action<object> onSolutionStart,
            Action<object> onSolutionEnd)
        {
            if (document is null)
            {
                return GhSolutionLifecycleSubscription.Unavailable("solution_document_missing");
            }

            if (onSolutionStart is null || onSolutionEnd is null)
            {
                return GhSolutionLifecycleSubscription.Unavailable("solution_lifecycle_callback_missing");
            }

            var documentType = document.GetType();
            var solutionStart = documentType.GetEvent("SolutionStart", BindingFlags.Instance | BindingFlags.Public);
            if (solutionStart is null)
            {
                return GhSolutionLifecycleSubscription.Unavailable("solution_start_event_missing");
            }

            var solutionEnd = documentType.GetEvent("SolutionEnd", BindingFlags.Instance | BindingFlags.Public);
            if (solutionEnd is null)
            {
                return GhSolutionLifecycleSubscription.Unavailable("solution_end_event_missing");
            }

            if (!TryCreateHandler(solutionStart, onSolutionStart, out var startHandler) ||
                !TryCreateHandler(solutionEnd, onSolutionEnd, out var endHandler))
            {
                return GhSolutionLifecycleSubscription.Unavailable("solution_lifecycle_delegate_incompatible");
            }

            try
            {
                solutionStart.AddEventHandler(document, startHandler);
                try
                {
                    solutionEnd.AddEventHandler(document, endHandler);
                }
                catch
                {
                    solutionStart.RemoveEventHandler(document, startHandler);
                    throw;
                }

                return GhSolutionLifecycleSubscription.Available(
                    document,
                    solutionStart,
                    startHandler,
                    solutionEnd,
                    endHandler);
            }
            catch
            {
                return GhSolutionLifecycleSubscription.Unavailable("solution_lifecycle_subscribe_failed");
            }
        }

        private static bool TryCreateHandler(EventInfo eventInfo, Action<object> callback, out Delegate handler)
        {
            handler = null!;
            var delegateType = eventInfo.EventHandlerType;
            var invoke = delegateType?.GetMethod("Invoke", BindingFlags.Instance | BindingFlags.Public);
            var parameters = invoke?.GetParameters();
            if (invoke is null ||
                parameters is null ||
                invoke.ReturnType != typeof(void) ||
                parameters.Length != 2 ||
                parameters[0].ParameterType != typeof(object) ||
                !typeof(EventArgs).IsAssignableFrom(parameters[1].ParameterType))
            {
                return false;
            }

            var documentProperty = parameters[1].ParameterType.GetProperty("Document", BindingFlags.Instance | BindingFlags.Public);
            if (documentProperty?.CanRead != true || documentProperty.GetMethod is null)
            {
                return false;
            }

            try
            {
                var sender = Expression.Parameter(parameters[0].ParameterType, "sender");
                var eventArgs = Expression.Parameter(parameters[1].ParameterType, "eventArgs");
                var document = Expression.Property(eventArgs, documentProperty);
                var invokeCallback = Expression.Call(
                    Expression.Constant(callback),
                    typeof(Action<object>).GetMethod(nameof(Action<object>.Invoke))!,
                    Expression.Convert(document, typeof(object)));

                handler = Expression.Lambda(delegateType!, invokeCallback, sender, eventArgs).Compile();
                return true;
            }
            catch
            {
                return false;
            }
        }
    }

    internal sealed class GhSolutionLifecycleSubscription : IDisposable
    {
        private readonly object? _document;
        private readonly EventInfo? _solutionStart;
        private readonly Delegate? _startHandler;
        private readonly EventInfo? _solutionEnd;
        private readonly Delegate? _endHandler;
        private int _disposed;

        private GhSolutionLifecycleSubscription(
            bool isAvailable,
            string? reason,
            object? document = null,
            EventInfo? solutionStart = null,
            Delegate? startHandler = null,
            EventInfo? solutionEnd = null,
            Delegate? endHandler = null)
        {
            IsAvailable = isAvailable;
            Reason = reason;
            _document = document;
            _solutionStart = solutionStart;
            _startHandler = startHandler;
            _solutionEnd = solutionEnd;
            _endHandler = endHandler;
        }

        internal bool IsAvailable { get; }
        internal string? Reason { get; }

        internal static GhSolutionLifecycleSubscription Unavailable(string reason) => new(false, reason);

        internal static GhSolutionLifecycleSubscription Available(
            object document,
            EventInfo solutionStart,
            Delegate startHandler,
            EventInfo solutionEnd,
            Delegate endHandler) =>
            new(true, null, document, solutionStart, startHandler, solutionEnd, endHandler);

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0 ||
                _document is null ||
                _solutionStart is null ||
                _startHandler is null ||
                _solutionEnd is null ||
                _endHandler is null)
            {
                return;
            }

            try
            {
                _solutionStart.RemoveEventHandler(_document, _startHandler);
            }
            finally
            {
                _solutionEnd.RemoveEventHandler(_document, _endHandler);
            }
        }
    }
}
