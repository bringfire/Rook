using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.Revit.UI;

namespace RookBim.Revit
{
    public sealed class RevitApiDispatcher : IExternalEventHandler
    {
        private readonly ConcurrentQueue<IRevitApiWorkItem> queue = new ConcurrentQueue<IRevitApiWorkItem>();
        private readonly ExternalEvent? externalEvent;
        private readonly Exception? creationException;

        public RevitApiDispatcher()
        {
            try
            {
                externalEvent = ExternalEvent.Create(this);
            }
            catch (Exception ex)
            {
                creationException = ex;
            }
        }

        public Task<T> Invoke<T>(Func<UIApplication, T> work)
        {
            return InvokeAbandonable(work).Task;
        }

        internal RevitApiDispatch<T> InvokeAbandonable<T>(Func<UIApplication, T> work)
        {
            if (work == null)
            {
                throw new ArgumentNullException(nameof(work));
            }

            if (creationException != null)
            {
                return RevitApiDispatch<T>.FromException(creationException);
            }

            if (externalEvent == null)
            {
                return RevitApiDispatch<T>.FromException(
                    new InvalidOperationException("Revit external event was not created."));
            }

            var item = new RevitApiWorkItem<T>(work);
            queue.Enqueue(item);
            var dispatch = new RevitApiDispatch<T>(item.Task, item.TryAbandon);

            ExternalEventRequest request;
            try
            {
                request = externalEvent.Raise();
            }
            catch (Exception ex)
            {
                item.TrySetException(ex);
                return dispatch;
            }

            if (request != ExternalEventRequest.Accepted && request != ExternalEventRequest.Pending)
            {
                item.TrySetException(
                    new InvalidOperationException($"Revit external event request was {request}."));
            }

            return dispatch;
        }

        public void Execute(UIApplication uiapp)
        {
            while (queue.TryDequeue(out var item))
            {
                item.Execute(uiapp);
            }
        }

        public string GetName()
        {
            return "RookBim Revit API Dispatcher";
        }

        private interface IRevitApiWorkItem
        {
            void Execute(UIApplication uiapp);
        }

        internal sealed class RevitApiDispatch<T>
        {
            private readonly Func<bool> abandon;

            public RevitApiDispatch(Task<T> task, Func<bool> abandon)
            {
                Task = task ?? throw new ArgumentNullException(nameof(task));
                this.abandon = abandon ?? throw new ArgumentNullException(nameof(abandon));
            }

            public Task<T> Task { get; }

            public bool Abandon()
            {
                return abandon();
            }

            public static RevitApiDispatch<T> FromException(Exception ex)
            {
                var completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
                completion.SetException(ex);
                return new RevitApiDispatch<T>(completion.Task, () => false);
            }
        }

        private sealed class RevitApiWorkItem<T> : IRevitApiWorkItem
        {
            private const int Pending = 0;
            private const int Running = 1;
            private const int Completed = 2;
            private const int Abandoned = 3;

            private readonly Func<UIApplication, T> work;
            private readonly TaskCompletionSource<T> completion =
                new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
            private int state = Pending;

            public RevitApiWorkItem(Func<UIApplication, T> work)
            {
                this.work = work;
            }

            public Task<T> Task
            {
                get { return completion.Task; }
            }

            public void Execute(UIApplication uiapp)
            {
                if (Interlocked.CompareExchange(ref state, Running, Pending) != Pending)
                {
                    return;
                }

                try
                {
                    completion.TrySetResult(work(uiapp));
                }
                catch (Exception ex)
                {
                    completion.TrySetException(ex);
                }
                finally
                {
                    Volatile.Write(ref state, Completed);
                }
            }

            public void TrySetException(Exception ex)
            {
                if (Interlocked.CompareExchange(ref state, Completed, Pending) == Pending)
                {
                    completion.TrySetException(ex);
                }
            }

            public bool TryAbandon()
            {
                if (Interlocked.CompareExchange(ref state, Abandoned, Pending) != Pending)
                {
                    return false;
                }

                completion.TrySetCanceled();
                return true;
            }
        }
    }
}
