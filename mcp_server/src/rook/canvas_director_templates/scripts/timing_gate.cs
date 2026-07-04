using System;
using Grasshopper;
using Grasshopper.Kernel;

public class Script_Instance : GH_ScriptInstance
{
    private bool _hasLatch;
    private bool _lastTrigger;
    private int _startFrame;

    private void RunScript(
		object GlobalFrame,
		object Trigger,
		object Delay,
		object Duration,
		object Reset,
		ref object LocalT,
		ref object Active,
		ref object Started,
		ref object Done,
		ref object StartFrame,
		ref object EndFrame,
		ref object Info)
    {
        int frame = Math.Max(0, ReadInt(GlobalFrame, 0));
        bool trigger = ReadBool(Trigger, false);
        int delay = Math.Max(0, ReadInt(Delay, 0));
        int duration = Math.Max(1, ReadInt(Duration, 60));
        bool reset = ReadBool(Reset, false);

        if (reset || !trigger)
        {
            _hasLatch = false;
            _lastTrigger = trigger;
        }

        bool risingEdge = trigger && !_lastTrigger;
        if (trigger && (!_hasLatch || risingEdge))
        {
            _startFrame = frame + delay;
            _hasLatch = true;
        }

        int endFrame = _hasLatch ? _startFrame + duration : -1;
        bool started = _hasLatch && frame >= _startFrame;
        bool done = _hasLatch && frame >= endFrame;
        bool active = trigger && started && !done;
        double localT = 0.0;

        if (_hasLatch && started)
            localT = Clamp((double)(frame - _startFrame) / (double)duration, 0.0, 1.0);

        LocalT = localT;
        Active = active || done;
        Started = started;
        Done = done;
        StartFrame = _hasLatch ? _startFrame : -1;
        EndFrame = endFrame;
        Info = $"Director Timing Gate: frame={frame}; trigger={trigger}; delay={delay}; duration={duration}; latched={_hasLatch}; start={(_hasLatch ? _startFrame.ToString() : "none")}; end={(_hasLatch ? endFrame.ToString() : "none")}; localT={localT:0.###}; active={active}; started={started}; done={done}; mode=trigger-latch-reset-on-false.";

        _lastTrigger = trigger;
    }

    private static int ReadInt(object value, int fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToInt32(value); }
        catch { return fallback; }
    }

    private static bool ReadBool(object value, bool fallback)
    {
        if (value == null) return fallback;
        try { return Convert.ToBoolean(value); }
        catch { return fallback; }
    }

    private static double Clamp(double value, double min, double max)
    {
        if (value < min) return min;
        if (value > max) return max;
        return value;
    }
}
