using System;

namespace RookBim.Revit
{
    /// <summary>
    /// The wait for Revit's idle queue ran out. <see cref="WorkStarted"/> tells
    /// the two very different cases apart: Revit never became idle (the work
    /// was withdrawn and never ran), or the work is running and is merely slow.
    /// </summary>
    internal sealed class RevitDispatchTimeoutException : TimeoutException
    {
        public RevitDispatchTimeoutException(bool workStarted, TimeSpan waited)
            : base(workStarted
                ? $"The work started on Revit's API thread but did not finish within {Seconds(waited)} s."
                : $"Revit did not become idle within {Seconds(waited)} s.")
        {
            WorkStarted = workStarted;
            Waited = waited;
        }

        public bool WorkStarted { get; }

        public TimeSpan Waited { get; }

        internal static string Seconds(TimeSpan value)
        {
            return ((int)Math.Round(value.TotalSeconds)).ToString(
                System.Globalization.CultureInfo.InvariantCulture);
        }
    }
}
