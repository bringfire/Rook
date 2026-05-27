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
        private const string RhinocerosTypeName = "RhinoInside.Revit.Rhinoceros";
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

            var cancellation = new CancellationTokenSource();
            var task = Task.Run(
                () => InvokeInHostContext(work, cancellation.Token),
                cancellation.Token);

            return new RevitApiDispatch<T>(
                task,
                () =>
                {
                    if (task.IsCompleted)
                    {
                        return false;
                    }

                    cancellation.Cancel();
                    return true;
                });
        }

        private static T InvokeInHostContext<T>(Func<UIApplication, T> work, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();

            var rhinocerosType = ResolveRhinoInsideType(RhinocerosTypeName);
            var invokeMethod = ResolveInvokeInHostContext(rhinocerosType).MakeGenericMethod(typeof(T));
            var revitType = ResolveRhinoInsideType(RevitTypeName);
            var activeApplicationProperty = ResolveActiveUIApplication(revitType);

            Func<T> hostWork = () =>
            {
                cancellationToken.ThrowIfCancellationRequested();

                var uiapp = activeApplicationProperty.GetValue(null, null) as UIApplication;
                if (uiapp == null)
                {
                    throw new InvalidOperationException("RhinoInside.Revit reported no active UIApplication.");
                }

                return work(uiapp);
            };

            try
            {
                return (T)invokeMethod.Invoke(null, new object[] { hostWork });
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

        private static MethodInfo ResolveInvokeInHostContext(Type rhinocerosType)
        {
            var method = rhinocerosType
                .GetMethods(BindingFlags.Public | BindingFlags.Static)
                .SingleOrDefault(candidate =>
                    candidate.Name == "InvokeInHostContext" &&
                    candidate.IsGenericMethodDefinition &&
                    candidate.GetParameters().Length == 1);

            if (method == null)
            {
                throw new MissingMethodException(
                    RhinocerosTypeName,
                    "InvokeInHostContext<T>(Func<T>)");
            }

            return method;
        }

        private static PropertyInfo ResolveActiveUIApplication(Type revitType)
        {
            var property = revitType.GetProperty(
                "ActiveUIApplication",
                BindingFlags.Public | BindingFlags.Static);

            if (property == null)
            {
                throw new MissingMemberException(RevitTypeName, "ActiveUIApplication");
            }

            return property;
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
    }
}
