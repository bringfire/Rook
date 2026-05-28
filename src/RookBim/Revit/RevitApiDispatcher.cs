using System;
using System.Linq;
using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.Revit.UI;

namespace RookBim.Revit
{
    public sealed class RevitApiDispatcher
    {
        private const string RhinoInsideAssemblyName = "RhinoInside.Revit";
        private const string RevitTypeName = "RhinoInside.Revit.Revit";

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

            var item = new RevitApiWorkItem<T>(work);
            try
            {
                EnqueueIdlingAction(new Action(item.Execute));
            }
            catch (Exception ex)
            {
                item.TrySetException(ex);
            }

            return new RevitApiDispatch<T>(item.Task, item.TryAbandon);
        }

        private static void EnqueueIdlingAction(Action action)
        {
            var revitType = ResolveRhinoInsideType(RevitTypeName);
            var method = revitType.GetMethod(
                "EnqueueIdlingAction",
                BindingFlags.NonPublic | BindingFlags.Static,
                binder: null,
                types: new[] { typeof(Action) },
                modifiers: null);

            if (method == null)
            {
                throw new MissingMethodException(RevitTypeName, "EnqueueIdlingAction(Action)");
            }

            try
            {
                method.Invoke(null, new object[] { action });
            }
            catch (TargetInvocationException ex) when (ex.InnerException != null)
            {
                ExceptionDispatchInfo.Capture(ex.InnerException).Throw();
                throw;
            }
        }

        private static UIApplication ActiveUIApplication()
        {
            var revitType = ResolveRhinoInsideType(RevitTypeName);
            var property = revitType.GetProperty(
                "ActiveUIApplication",
                BindingFlags.Public | BindingFlags.Static);

            if (property == null)
            {
                throw new MissingMemberException(RevitTypeName, "ActiveUIApplication");
            }

            try
            {
                var uiapp = property.GetValue(null, null) as UIApplication;
                if (uiapp == null)
                {
                    throw new InvalidOperationException("RhinoInside.Revit reported no active UIApplication.");
                }

                return uiapp;
            }
            catch (TargetInvocationException ex) when (ex.InnerException != null)
            {
                ExceptionDispatchInfo.Capture(ex.InnerException).Throw();
                throw;
            }
        }

        private static Type ResolveRhinoInsideType(string typeName)
        {
            var type = Type.GetType(typeName + ", " + RhinoInsideAssemblyName, throwOnError: false);
            if (type != null)
            {
                return type;
            }

            var assembly = AppDomain.CurrentDomain
                .GetAssemblies()
                .FirstOrDefault(candidate =>
                    string.Equals(
                        candidate.GetName().Name,
                        RhinoInsideAssemblyName,
                        StringComparison.OrdinalIgnoreCase));

            type = assembly?.GetType(typeName, throwOnError: false);
            if (type != null)
            {
                return type;
            }

            throw new InvalidOperationException(RhinoInsideAssemblyName + " is not loaded.");
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
        }

        private sealed class RevitApiWorkItem<T>
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

            public void Execute()
            {
                if (Interlocked.CompareExchange(ref state, Running, Pending) != Pending)
                {
                    return;
                }

                try
                {
                    completion.TrySetResult(work(ActiveUIApplication()));
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
