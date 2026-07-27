using System;
using System.Threading.Tasks;

namespace Rook.Bim
{
    internal static class BimCreationGuidProbeDispatchAwaiter
    {
        internal static T Wait<T>(Task<T> task, Func<bool> tryAbandon, TimeSpan timeout)
        {
            if (Task.WaitAny(new Task[] { task }, timeout) < 0 && tryAbandon())
            {
                throw new TimeoutException(
                    "Timed out waiting for RhinoInside Revit idling-queue execution.");
            }

            return task.GetAwaiter().GetResult();
        }
    }
}
